"""生成工作狀態（架構書 §6.2；spec 0006）。純領域邏輯，不依賴供應商或資料庫。"""

from datetime import datetime
from enum import StrEnum

from app.domain.ports import GenerationJob


class JobStatus(StrEnum):
    QUEUED = "queued"
    SUBMITTED = "submitted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    STORED = "stored"
    FAILED = "failed"
    FAILED_FINAL = "failed_final"


MAX_ATTEMPTS = 2  # 自動重試 1 次


class InvalidJobTransition(Exception):
    def __init__(self, status: str, to: JobStatus) -> None:
        self.status = status
        self.to = to
        super().__init__(f"生成工作狀態 {status} 不可轉為 {to}")


def advance(job: GenerationJob, to: JobStatus, *, error: str | None = None) -> None:
    raise NotImplementedError


def should_retry(attempt: int, retryable: bool) -> bool:
    raise NotImplementedError


def timed_out(submitted_at: datetime, now: datetime, timeout_s: float) -> bool:
    raise NotImplementedError
