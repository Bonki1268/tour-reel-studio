"""核准與失效（架構書 §6.3；spec 0003）。純領域邏輯，不依賴資料庫或框架。"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.video import Video, utc_now


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


def canonical_hash(obj: object) -> str:
    raise NotImplementedError


def plan_approval_input(
    plan: Mapping[str, object], placements: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    raise NotImplementedError


def approve_plan(
    video: Video,
    plan: Mapping[str, object],
    placements: Sequence[Mapping[str, object]],
    cost_cap: Decimal,
    approved_by: str,
) -> Approval:
    raise NotImplementedError


def auto_approve(
    kind: ApprovalKind, content: object, *, clock: Callable[[], datetime] = utc_now
) -> Approval:
    raise NotImplementedError


def ensure_still_approved(approval: Approval, current_input: object) -> None:
    raise NotImplementedError


def check_before_submit(video: Video, approval: Approval, current_input: object) -> None:
    raise NotImplementedError
