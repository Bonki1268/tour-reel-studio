"""成本估算與預算控制（架構書 §6.4；spec 0004）。點數以 Decimal 表示，不使用浮點數。"""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Literal


class JobKind(StrEnum):
    KEYFRAME = "keyframe"
    VIDEO = "video"


class CostTableError(ValueError):
    """單價表缺少模型，或單價表檔案不合法。"""


@dataclass(frozen=True)
class CostTable:
    prices: Mapping[tuple[JobKind, str], Decimal]

    @classmethod
    def load(cls, path: Path) -> "CostTable":
        """讀取 COST_TABLE 指定的 JSON 檔；任何問題都以 CostTableError 說明檔案與原因。"""
        if not path.is_file():
            raise CostTableError(f"單價表 {path} 不存在")
        try:
            data = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
        except json.JSONDecodeError as e:
            raise CostTableError(f"單價表 {path} 不是合法的 JSON：{e.msg}（第 {e.lineno} 行）") from None
        if not isinstance(data, dict) or not isinstance(data.get("prices"), list):
            raise CostTableError(f"單價表 {path} 缺少 prices 串列")
        try:
            return cls.from_rows(data["prices"])
        except CostTableError as e:
            raise CostTableError(f"單價表 {path}：{e}") from None

    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, object]]) -> "CostTable":
        prices: dict[tuple[JobKind, str], Decimal] = {}
        for n, row in enumerate(rows, start=1):
            key, credits = _parse_row(n, row)
            if key in prices:
                raise CostTableError(f"第 {n} 筆與前面重複：{key[0]}／{key[1]}")
            prices[key] = credits
        return cls(MappingProxyType(prices))

    def price(self, kind: JobKind, model: str) -> Decimal:
        try:
            return self.prices[(kind, model)]
        except KeyError:
            raise CostTableError(f"單價表缺少 {kind}／{model} 的單價") from None


def _parse_row(n: int, row: object) -> tuple[tuple[JobKind, str], Decimal]:
    if not isinstance(row, Mapping):
        raise CostTableError(f"第 {n} 筆不是物件")
    for name in ("kind", "model", "credits"):
        if row.get(name) in (None, ""):
            raise CostTableError(f"第 {n} 筆缺少 {name}")
    try:
        kind = JobKind(row["kind"])
    except ValueError:
        raise CostTableError(f"第 {n} 筆是未知的工作種類：{row['kind']}") from None
    raw = row["credits"]
    try:
        if isinstance(raw, bool | float):
            raise InvalidOperation
        credits = Decimal(str(raw))
    except InvalidOperation:
        raise CostTableError(f"第 {n} 筆的 credits 不是數字：{raw}") from None
    if not credits.is_finite():
        raise CostTableError(f"第 {n} 筆的 credits 不是數字：{raw}")
    if credits < 0:
        raise CostTableError(f"第 {n} 筆的單價不可為負數：{credits}")
    return (kind, str(row["model"])), credits


@dataclass(frozen=True)
class Estimate:
    total: Decimal
    reserve: Decimal
    cap: Decimal


def estimate_video(
    table: CostTable, shot_count: int, image_model: str, video_model: str, reserve_shots: int = 1
) -> Estimate:
    """每鏡＝關鍵幀＋圖生影片；上限＝預估＋預留鏡數 × 單鏡完整重生成本的最大值。"""
    if shot_count < 0 or reserve_shots < 0:
        raise ValueError("鏡頭數與預留鏡數不可為負數")
    per_shot = [
        table.price(JobKind.KEYFRAME, image_model) + table.price(JobKind.VIDEO, video_model)
        for _ in range(shot_count)
    ]
    total = sum(per_shot, Decimal(0))
    reserve = max(per_shot, default=Decimal(0)) * reserve_shots
    return Estimate(total=total, reserve=reserve, cap=total + reserve)


class BudgetExceeded(Exception):
    """送出此工作會超出使用者核准的成本上限。"""

    requires_reconfirmation = True

    def __init__(self, cap: Decimal, committed: Decimal, requested: Decimal) -> None:
        self.cap = cap
        self.committed = committed
        self.requested = requested
        super().__init__(f"超出預算上限：上限 {cap} 點，已承諾 {committed} 點，此工作預估 {requested} 點")


@dataclass(frozen=True)
class CostEntry:
    job_id: str
    credits: Decimal
    source: Literal["provider", "table"]


@dataclass
class Budget:
    cap: Decimal
    entries: list[CostEntry] = field(default_factory=list)
    reserved: dict[str, Decimal] = field(default_factory=dict)

    @property
    def spent(self) -> Decimal:
        return sum((e.credits for e in self.entries), Decimal(0))

    def check(self, job_id: str, estimate: Decimal) -> None:
        """送出前檢查：已花費＋其他進行中工作的預留＋此工作預估 ≤ 上限；通過即預留。"""
        if estimate < 0:
            raise ValueError("預估成本不可為負數")
        others = sum((v for k, v in self.reserved.items() if k != job_id), Decimal(0))
        committed = self.spent + others
        if committed + estimate > self.cap:
            raise BudgetExceeded(self.cap, committed, estimate)
        self.reserved[job_id] = estimate

    def release(self, job_id: str) -> None:
        """釋放工作的預留額度（失敗的嘗試；spec 0006 R-007）。"""
        self.reserved.pop(job_id, None)

    def record(
        self, job_id: str, kind: JobKind, model: str, actual: Decimal | None, table: CostTable
    ) -> CostEntry | None:
        """以實際成本記帳（未回報時用單價表）並釋放預留；同一工作已記帳則回傳 None。"""
        if any(e.job_id == job_id for e in self.entries):
            return None
        if actual is not None and actual < 0:
            raise ValueError("實際成本不可為負數")
        entry = (
            CostEntry(job_id, actual, "provider")
            if actual is not None
            else CostEntry(job_id, table.price(kind, model), "table")
        )
        self.entries.append(entry)
        self.reserved.pop(job_id, None)
        return entry
