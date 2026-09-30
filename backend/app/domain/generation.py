"""生成工作狀態（架構書 §6.2；spec 0006）。純領域邏輯，不依賴供應商或資料庫。"""

from datetime import datetime, timedelta
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


_J = JobStatus
TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    _J.QUEUED: frozenset({_J.SUBMITTED, _J.FAILED}),
    _J.SUBMITTED: frozenset({_J.RUNNING, _J.SUCCEEDED, _J.FAILED}),
    _J.RUNNING: frozenset({_J.SUCCEEDED, _J.FAILED}),
    _J.SUCCEEDED: frozenset({_J.STORED, _J.FAILED}),  # 下載或轉存失敗
    _J.FAILED: frozenset({_J.FAILED_FINAL}),
}

MAX_ATTEMPTS = 2  # 自動重試 1 次


class InvalidJobTransition(Exception):
    def __init__(self, status: str, to: JobStatus) -> None:
        self.status = status
        self.to = to
        super().__init__(f"生成工作狀態 {status} 不可轉為 {to}")


def advance(job: GenerationJob, to: JobStatus, *, error: str | None = None) -> None:
    """依轉換表轉換；不合法時拋出 InvalidJobTransition，工作不變。"""
    if to not in TRANSITIONS.get(JobStatus(job.status), frozenset()):
        raise InvalidJobTransition(job.status, to)
    job.status = to
    if error is not None:
        job.error = error


def should_retry(attempt: int, retryable: bool) -> bool:
    return retryable and attempt < MAX_ATTEMPTS


def timed_out(submitted_at: datetime, now: datetime, timeout_s: float) -> bool:
    return now - submitted_at >= timedelta(seconds=timeout_s)
