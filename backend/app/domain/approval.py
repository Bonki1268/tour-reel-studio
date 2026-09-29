"""核准與失效（架構書 §6.3；spec 0003）。純領域邏輯，不依賴資料庫或框架。"""

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.domain.video import Video, VideoEvent, utc_now


class ApprovalKind(StrEnum):
    PLAN = "plan"
    FINAL = "final"
    SCRIPT = "script"
    ASSETS = "assets"
    KEYFRAMES = "keyframes"


# 需要使用者親自確認、不可由系統自動核准的類型
USER_ONLY_KINDS = frozenset({ApprovalKind.PLAN, ApprovalKind.FINAL})


class ApprovalError(ValueError):
    """核准紀錄本身不合法。"""


class ApprovalInvalidated(Exception):
    """核准後內容被修改，核准已失效。"""

    def __init__(self, kind: ApprovalKind, approved_hash: str, current_hash: str) -> None:
        self.kind = kind
        self.approved_hash = approved_hash
        self.current_hash = current_hash
        super().__init__(f"{kind} 核准已失效：核准時 {approved_hash[:12]}，目前 {current_hash[:12]}")


@dataclass(frozen=True)
class Approval:
    kind: ApprovalKind
    input_hash: str
    cost_cap: Decimal | None
    auto_approved: bool
    approved_by: str | None
    approved_at: datetime

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "kind", ApprovalKind(self.kind))
        except ValueError:
            raise ApprovalError(f"未知的核准類型：{self.kind}") from None
        if self.cost_cap is not None and self.cost_cap <= 0:
            raise ApprovalError("成本上限必須為正數")
        if self.kind == ApprovalKind.PLAN and self.cost_cap is None:
            raise ApprovalError("企劃核准必須有成本上限")
        if self.auto_approved:
            if self.kind in USER_ONLY_KINDS:
                raise ApprovalError(f"{self.kind} 必須由使用者確認，不可自動核准")
            if self.approved_by is not None:
                raise ApprovalError("系統自動核准不應有核准者")
        elif not (self.approved_by and self.approved_by.strip()):
            raise ApprovalError("使用者核准必須有核准者")


_FLOAT_STEP = Decimal("0.0001")


def _normalize(obj: object) -> object:
    """轉成可穩定序列化的結構；浮點數固定到小數 4 位，整數值的浮點數視同整數。"""
    if obj is None or isinstance(obj, bool | int | str):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(f"輸入雜湊不接受 {obj}")
        # 以十進位最短表示四捨五入，避免二進位誤差（例如 0.1 + 0.2）
        q = Decimal(repr(obj)).quantize(_FLOAT_STEP, rounding=ROUND_HALF_UP)
        return int(q) if q == q.to_integral_value() else float(q)
    if isinstance(obj, Decimal):
        return str(obj.normalize())
    if isinstance(obj, Mapping):
        if not all(isinstance(k, str) for k in obj):
            raise TypeError("輸入雜湊的字典鍵必須是字串")
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_normalize(v) for v in obj]
    raise TypeError(f"輸入雜湊不支援的型別：{type(obj).__name__}")


def canonical_hash(obj: object) -> str:
    """內容雜湊：與字典鍵順序無關、與串列順序有關（SHA-256 十六進位）。"""
    text = json.dumps(_normalize(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plan_approval_input(
    plan: Mapping[str, object], placements: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """企劃核准涵蓋的內容：選定企劃＋依鏡頭編號排序的擺放。"""
    return {"plan": plan, "placements": sorted(placements, key=_shot_no)}


def _shot_no(placement: Mapping[str, object]) -> int:
    shot_no = placement["shot_no"]
    if not isinstance(shot_no, int):
        raise TypeError("擺放的 shot_no 必須是整數")
    return shot_no


def approve_plan(
    video: Video,
    plan: Mapping[str, object],
    placements: Sequence[Mapping[str, object]],
    cost_cap: Decimal,
    approved_by: str,
) -> Approval:
    """使用者核准企劃與成本上限；影片由 plan_ready 進入 generating。"""
    approval = Approval(
        kind=ApprovalKind.PLAN,
        input_hash=canonical_hash(plan_approval_input(plan, placements)),
        cost_cap=cost_cap,
        auto_approved=False,
        approved_by=approved_by,
        approved_at=video.clock(),
    )
    video.apply(VideoEvent.APPROVE_PLAN)
    return approval


def auto_approve(
    kind: ApprovalKind, content: object, *, clock: Callable[[], datetime] = utc_now
) -> Approval:
    """快速模式中系統自動採用的項目。"""
    return Approval(
        kind=kind,
        input_hash=canonical_hash(content),
        cost_cap=None,
        auto_approved=True,
        approved_by=None,
        approved_at=clock(),
    )


def ensure_still_approved(approval: Approval, current_input: object) -> None:
    current = canonical_hash(current_input)
    if current != approval.input_hash:
        raise ApprovalInvalidated(approval.kind, approval.input_hash, current)


def check_before_submit(video: Video, approval: Approval, current_input: object) -> None:
    """送出生成工作前檢查；核准失效時影片退回 plan_ready 並拋出 ApprovalInvalidated。"""
    try:
        ensure_still_approved(approval, current_input)
    except ApprovalInvalidated:
        video.apply(VideoEvent.APPROVAL_INVALIDATED)
        raise
