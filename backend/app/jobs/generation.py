"""生成工作執行：核准檢查 → 預算檢查 → 送出 → 等待 → 轉存 → 記帳（架構書 §6.2；spec 0006）。

每次嘗試是一筆 generation_jobs 紀錄（spec 0006 待決事項 1）；每次狀態變更都寫入 repository。
"""

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.domain.approval import Approval, ApprovalInvalidated, canonical_hash, check_before_submit
from app.domain.cost import Budget, BudgetExceeded, CostTable, JobKind
from app.domain.generation import MAX_ATTEMPTS, JobStatus, advance, should_retry, timed_out
from app.domain.ids import idempotency_key, new_id
from app.domain.ports import GenerationJob, Repositories, Shot, ShotTake, Storage, VideoRecord
from app.domain.video import VideoEvent, VideoStatus, utc_now
from app.providers.base import (
    ImageProvider,
    ProviderError,
    ProviderJob,
    ProviderRequest,
    ProviderResult,
    ResultSource,
    VideoProvider,
)

# 架構書 §7 物件儲存路徑的檔名
RESULT_FILES = {JobKind.KEYFRAME: "keyframe.png", JobKind.VIDEO: "clip.mp4"}

_URL_QUERY = re.compile(r"(https?://[^\s?]+)\?\S*")


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
    provider_name: str = "higgsfield"  # 送出前的預設值；送出後以 ProviderJob.provider 為準
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


class _AttemptFailed(Exception):
    def __init__(self, message: str, retryable: bool) -> None:
        self.message = message
        self.retryable = retryable
        super().__init__(message)


def _describe(error: Exception) -> str:
    """錯誤訊息不保留網址的查詢參數（可能含簽章）。"""
    return _URL_QUERY.sub(r"\1?<已遮蔽>", f"{type(error).__name__}: {error}")


def _model(settings: Settings, kind: JobKind) -> str:
    return settings.hf_image_model if kind == JobKind.KEYFRAME else settings.hf_video_model


def _input_hash(spec: JobSpec) -> str:
    # 納入鏡頭版本：同一鏡重生時即使輸入相同也是新的工作（spec 0006 待決事項 2）
    return canonical_hash({"shot_take_attempt": spec.take.attempt, "input": spec.input_snapshot})


def build_attempt(ctx: GenerationContext, spec: JobSpec, attempt: int) -> GenerationJob:
    """第 attempt 次嘗試的工作紀錄（尚未寫入）；冪等鍵由規格內容決定。"""
    model = _model(ctx.settings, spec.kind)
    input_hash = _input_hash(spec)
    return GenerationJob(
        id=new_id(),
        shot_take_id=spec.take.id,
        idempotency_key=idempotency_key(spec.video.id, spec.shot.shot_no, spec.kind, input_hash, attempt),
        kind=spec.kind,
        provider=ctx.provider_name,
        model=model,
        input_hash=input_hash,
        attempt=attempt,
        status=JobStatus.QUEUED,
        input_snapshot=dict(spec.input_snapshot),
        provider_idempotency_key=new_id(),
        est_cost=ctx.cost_table.price(spec.kind, model),
    )


def result_key(spec: JobSpec) -> str:
    """架構書 §7：videos/{video_id}/shots/{shot_no}/take{n}/keyframe.png｜clip.mp4"""
    shot_dir = f"videos/{spec.video.id}/shots/{spec.shot.shot_no}/take{spec.take.attempt}"
    return f"{shot_dir}/{RESULT_FILES[spec.kind]}"


def _emit(ctx: GenerationContext, job: GenerationJob) -> None:
    ctx.events.append(JobEvent(job.id, job.attempt, JobStatus(job.status)))


async def _transition(
    ctx: GenerationContext, job: GenerationJob, to: JobStatus, *, error: str | None = None
) -> None:
    advance(job, to, error=error)
    await ctx.repos.jobs.update(job)
    _emit(ctx, job)


async def run_generation_job(ctx: GenerationContext, spec: JobSpec) -> GenerationJob:
    """執行並回傳最後一次嘗試；核准失效或超出預算時拋出 ApprovalInvalidated／BudgetExceeded。"""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        job, created = await ctx.repos.jobs.create_or_get(build_attempt(ctx, spec, attempt))
        if created:
            _emit(ctx, job)
        if job.status in (JobStatus.STORED, JobStatus.FAILED_FINAL):
            return job
        if job.status == JobStatus.FAILED and attempt < MAX_ATTEMPTS:
            continue  # 先前已失敗並決定重試
        try:
            await _run_attempt(ctx, spec, job)
            return job
        except _AttemptFailed as failure:
            await _transition(ctx, job, JobStatus.FAILED, error=failure.message)
            ctx.budget.release(job.id)
            if should_retry(attempt, failure.retryable):
                continue
            await _transition(ctx, job, JobStatus.FAILED_FINAL)
            # 多鏡同時失敗時，影片只進入一次 needs_attention（spec 0007 待決事項 1）
            if spec.video.video.status == VideoStatus.GENERATING:
                spec.video.video.apply(VideoEvent.SHOT_FAILED_FINAL)
                await ctx.repos.videos.save(spec.video)
            return job
    return job


async def _run_attempt(ctx: GenerationContext, spec: JobSpec, job: GenerationJob) -> None:
    if job.external_id is None:
        pjob = await _submit(ctx, spec, job)
    else:
        # 已送出（例如 Worker 重啟）：以既有 request ID 繼續查詢，不重新送出
        pjob = ProviderJob(job.provider, job.model, job.external_id, job.est_cost)
    result = await _wait(ctx, job, pjob)
    await _store(ctx, spec, job, result)


async def _submit(ctx: GenerationContext, spec: JobSpec, job: GenerationJob) -> ProviderJob:
    try:
        check_before_submit(spec.video.video, spec.approval, spec.approval_input)
    except ApprovalInvalidated:
        job.error = "approval_invalidated"
        await ctx.repos.jobs.update(job)
        await ctx.repos.videos.save(spec.video)
        raise
    try:
        ctx.budget.check(job.id, job.est_cost or Decimal(0))
    except BudgetExceeded:
        job.error = "budget_exceeded"
        await ctx.repos.jobs.update(job)
        raise
    req = ProviderRequest(job.model, spec.input_snapshot, job.provider_idempotency_key or job.id)
    try:
        if spec.kind == JobKind.KEYFRAME:
            pjob = await ctx.image_provider.compose(req)
        else:
            pjob = await ctx.video_provider.image_to_video(req)
    except ProviderError as e:
        raise _AttemptFailed(_describe(e), e.retryable) from e
    job.external_id, job.provider = pjob.external_id, pjob.provider
    job.submitted_at = ctx.clock()
    job.error = None
    await _transition(ctx, job, JobStatus.SUBMITTED)
    return pjob


async def _wait(ctx: GenerationContext, job: GenerationJob, pjob: ProviderJob) -> ProviderResult:
    timeout = ctx.settings.generation_timeout_s
    submitted_at = job.submitted_at or ctx.clock()
    while True:
        try:
            result = await ctx.results.fetch_result(pjob)
        except ProviderError as e:
            raise _AttemptFailed(_describe(e), e.retryable) from e
        if result.state == "succeeded":
            return result
        if result.state == "failed":
            error = result.error or ProviderError("供應商回報失敗")
            raise _AttemptFailed(_describe(error), error.retryable)
        if job.status == JobStatus.SUBMITTED:
            await _transition(ctx, job, JobStatus.RUNNING)
        if timed_out(submitted_at, ctx.clock(), timeout):
            raise _AttemptFailed(f"timeout: 送出後超過 {timeout:g} 秒未完成", retryable=True)
        await ctx.sleep(ctx.settings.generation_poll_interval_s)


async def _store(ctx: GenerationContext, spec: JobSpec, job: GenerationJob, result: ProviderResult) -> None:
    await _transition(ctx, job, JobStatus.SUCCEEDED)
    key = result_key(spec)
    try:
        content, content_type = await ctx.results.download(result)
        await ctx.storage.put(key, content, content_type)
    except ProviderError as e:
        raise _AttemptFailed(_describe(e), e.retryable) from e
    except Exception as e:  # 下載或轉存失敗視為可重試
        raise _AttemptFailed(_describe(e), retryable=True) from e

    # 重新讀取鏡頭版本，避免覆寫同一版本另一種工作（關鍵幀／影片）寫入的路徑
    take = next(t for t in await ctx.repos.shots.takes(spec.shot.id) if t.id == spec.take.id)
    if spec.kind == JobKind.KEYFRAME:
        take = replace(take, keyframe_key=key)
    else:
        take = replace(take, clip_key=key)
    await ctx.repos.shots.update_take(take)

    job.actual_cost = result.actual_cost
    await _transition(ctx, job, JobStatus.STORED)
    entry = ctx.budget.record(job.id, spec.kind, job.model, result.actual_cost, ctx.cost_table)
    if entry is not None:
        await ctx.repos.costs.add(spec.video.id, entry)
