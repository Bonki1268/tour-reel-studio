"""生成工作執行：核准檢查 → 預算檢查 → 送出 → 等待 → 轉存 → 記帳（架構書 §6.2；spec 0006）。"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.config import Settings
from app.domain.approval import Approval
from app.domain.cost import Budget, CostTable, JobKind
from app.domain.generation import JobStatus
from app.domain.ports import GenerationJob, Repositories, Shot, ShotTake, Storage, VideoRecord
from app.domain.video import utc_now
from app.providers.base import ImageProvider, ResultSource, VideoProvider


@dataclass(frozen=True)
class JobEvent:
    job_id: str
    attempt: int
    status: JobStatus


@dataclass
class GenerationContext:
    repos: Repositories
    storage: Storage
    image_provider: ImageProvider
    video_provider: VideoProvider
    results: ResultSource
    budget: Budget
    cost_table: CostTable
    settings: Settings
    clock: Callable[[], datetime] = utc_now
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    events: list[JobEvent] = field(default_factory=list)


@dataclass(frozen=True)
class JobSpec:
    video: VideoRecord
    shot: Shot
    take: ShotTake
    kind: JobKind
    approval: Approval
    approval_input: object  # 目前的核准涵蓋內容，送出前與核准時的雜湊比對
    input_snapshot: Mapping[str, Any]


def build_attempt(ctx: GenerationContext, spec: JobSpec, attempt: int) -> GenerationJob:
    """第 attempt 次嘗試的工作紀錄（尚未寫入）；冪等鍵由規格內容決定。"""
    raise NotImplementedError


async def run_generation_job(ctx: GenerationContext, spec: JobSpec) -> GenerationJob:
    """執行並回傳最後一次嘗試；核准失效或超出預算時拋出 ApprovalInvalidated／BudgetExceeded。"""
    raise NotImplementedError
