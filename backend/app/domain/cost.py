"""成本估算與預算控制（架構書 §6.4；spec 0004）。點數以 Decimal 表示，不使用浮點數。"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
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
        raise NotImplementedError

    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, object]]) -> "CostTable":
        raise NotImplementedError

    def price(self, kind: JobKind, model: str) -> Decimal:
        raise NotImplementedError


@dataclass(frozen=True)
class Estimate:
    total: Decimal
    reserve: Decimal
    cap: Decimal


def estimate_video(
    table: CostTable, shot_count: int, image_model: str, video_model: str, reserve_shots: int = 1
) -> Estimate:
    raise NotImplementedError


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
        raise NotImplementedError

    def check(self, job_id: str, estimate: Decimal) -> None:
        raise NotImplementedError

    def record(
        self, job_id: str, kind: JobKind, model: str, actual: Decimal | None, table: CostTable
    ) -> CostEntry | None:
        raise NotImplementedError
