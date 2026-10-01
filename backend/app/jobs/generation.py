"""生成工作執行：核准檢查 → 預算檢查 → 送出 → 等待 → 轉存 → 記帳（架構書 §6.2；spec 0006）。

每次嘗試是一筆 generation_jobs 紀錄（spec 0006 待決事項 1）；每次狀態變更都寫入 repository。
"""

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, fields, replace
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
from app.storage import keys

# 架構書 §7 物件儲存路徑的檔名
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


class AttemptFailed(Exception):
    """本次嘗試失敗；recorded 為真時工作已由其他來源標記為 failed，不再重寫狀態。"""

    def __init__(self, message: str, retryable: bool, *, recorded: bool = False) -> None:
        self.message = message
        self.retryable = retryable
        self.recorded = recorded
        super().__init__(message)


class JobTaken(Exception):
    """條件更新失敗：工作狀態已被其他來源（webhook、另一個 Worker、恢復掃描）改變（spec 0018）。"""


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


def _emit(ctx: GenerationContext, job: GenerationJob) -> None:
    ctx.events.append(JobEvent(job.id, job.attempt, JobStatus(job.status)))


def _sync(job: GenerationJob, source: GenerationJob) -> None:
    """以資料庫中的內容更新呼叫端持有的工作物件。"""
    for f in fields(job):
        setattr(job, f.name, getattr(source, f.name))


async def _reload(ctx: GenerationContext, job: GenerationJob) -> None:
    current = await ctx.repos.jobs.get(job.id)
    if current is not None:
        _sync(job, current)


async def _transition(
    ctx: GenerationContext, job: GenerationJob, to: JobStatus, *, error: str | None = None
) -> None:
    """依轉換表轉換並以條件更新寫入；資料庫中的狀態已被改變時還原物件並拋出 JobTaken。"""
    expected = JobStatus(job.status)
    before = replace(job)
    advance(job, to, error=error)
    if not await ctx.repos.jobs.update_if(job, expected):
        _sync(job, before)
        raise JobTaken(job.id)
    _emit(ctx, job)


async def _adopt(ctx: GenerationContext, job: GenerationJob, video_id: str) -> None:
    """工作已由其他來源轉存：把成本帳中的紀錄同步到本地預算（不重複記帳）。"""
    if not any(e.job_id == job.id for e in ctx.budget.entries):
        ctx.budget.entries += [e for e in await ctx.repos.costs.list(video_id) if e.job_id == job.id]
    ctx.budget.release(job.id)


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
        except AttemptFailed as failure:
            if not failure.recorded and not await _mark_failed(ctx, spec, job, failure.message):
                return job  # 標記失敗前已由其他來源轉存完成
            ctx.budget.release(job.id)
            if should_retry(attempt, failure.retryable):
                continue
            try:
                await _transition(ctx, job, JobStatus.FAILED_FINAL)
            except JobTaken:
                await _reload(ctx, job)
            # 多鏡同時失敗時，影片只進入一次 needs_attention（spec 0007 待決事項 1）
            if spec.video.video.status == VideoStatus.GENERATING:
                spec.video.video.apply(VideoEvent.SHOT_FAILED_FINAL)
                await ctx.repos.videos.save(spec.video)
            return job
    return job


async def _mark_failed(ctx: GenerationContext, spec: JobSpec, job: GenerationJob, message: str) -> bool:
    """標記本次嘗試失敗；回傳 False 表示工作已由其他來源轉存（視為完成）。"""
    try:
        await _transition(ctx, job, JobStatus.FAILED, error=message)
        return True
    except JobTaken:
        await _reload(ctx, job)
        if job.status == JobStatus.STORED:
            await _adopt(ctx, job, spec.video.id)
            return False
        return True  # 其他來源已標記失敗


def _provider_job(job: GenerationJob) -> ProviderJob:
    return ProviderJob(job.provider, job.model, job.external_id or "", job.est_cost)


async def _run_attempt(ctx: GenerationContext, spec: JobSpec, job: GenerationJob) -> None:
    if job.external_id is None:
        try:
            pjob = await _submit(ctx, spec, job)
        except JobTaken:  # 另一個 Worker 同時送出（供應商以相同的冪等鍵去重）
            await _reload(ctx, job)
            pjob = _provider_job(job)
    else:
        # 已送出（例如 Worker 重啟）：以既有 request ID 繼續查詢，不重新送出
        pjob = _provider_job(job)
    await _wait(ctx, spec, job, pjob)


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
        raise AttemptFailed(_describe(e), e.retryable) from e
    job.external_id, job.provider = pjob.external_id, pjob.provider
    job.submitted_at = ctx.clock()
    job.error = None
    await _transition(ctx, job, JobStatus.SUBMITTED)
    return pjob


async def _wait(ctx: GenerationContext, spec: JobSpec, job: GenerationJob, pjob: ProviderJob) -> None:
    """輪詢直到工作 stored（由本次或其他來源轉存）；失敗或逾時拋出 AttemptFailed。"""
    timeout = ctx.settings.generation_timeout_s
    submitted_at = job.submitted_at or ctx.clock()
    while True:
        await _reload(ctx, job)  # 每次輪詢前讀取資料庫中的狀態：其他來源可能已處理
        if job.status == JobStatus.STORED:
            await _adopt(ctx, job, spec.video.id)
            return
        if job.status == JobStatus.FAILED:
            raise AttemptFailed(job.error or "其他來源標記為失敗", retryable=True, recorded=True)
        if job.status != JobStatus.SUCCEEDED:  # 他方轉存中時只等待，不查詢供應商
            try:
                result = await ctx.results.fetch_result(pjob)
            except ProviderError as e:
                raise AttemptFailed(_describe(e), e.retryable) from e
            if result.state == "succeeded":
                if await complete_job(ctx, job, result):
                    return
                continue  # 處理權已被取得：重新讀取狀態
            if result.state == "failed":
                error = result.error or ProviderError("供應商回報失敗")
                raise AttemptFailed(_describe(error), error.retryable)
            if job.status == JobStatus.SUBMITTED:
                try:
                    await _transition(ctx, job, JobStatus.RUNNING)
                except JobTaken:
                    continue
        if timed_out(submitted_at, ctx.clock(), timeout):
            raise AttemptFailed(f"timeout: 送出後超過 {timeout:g} 秒未完成", retryable=True)
        await ctx.sleep(ctx.settings.generation_poll_interval_s)


async def complete_job(ctx: GenerationContext, job: GenerationJob, result: ProviderResult) -> bool:
    """輪詢與 webhook 共用的結果處理（spec 0018 R-004）：以「submitted／running → succeeded」的條件更新
    取得處理權，只有取得者下載、轉存、更新鏡頭版本、標記 stored 並記帳。回傳是否由本次處理。

    轉存失敗時工作標記為 failed 並拋出 AttemptFailed（recorded），由輪詢端依重試規則處理。
    """
    if job.status not in (JobStatus.SUBMITTED, JobStatus.RUNNING):
        return False
    try:
        await _transition(ctx, job, JobStatus.SUCCEEDED)
    except JobTaken:
        return False

    take = await ctx.repos.shots.get_take(job.shot_take_id)
    shot = await ctx.repos.shots.get_shot(take.shot_id) if take is not None else None
    if take is None or shot is None:
        await _transition(ctx, job, JobStatus.FAILED, error="找不到工作所屬的鏡頭版本")
        raise AttemptFailed(job.error or "", retryable=False, recorded=True)
    make = keys.keyframe if job.kind == JobKind.KEYFRAME else keys.clip
    key = make(shot.video_id, shot.shot_no, take.attempt)
    try:
        content, content_type = await ctx.results.download(result)
        await ctx.storage.put(key, content, content_type)
    except Exception as e:  # 下載或轉存失敗視為可重試
        retryable = e.retryable if isinstance(e, ProviderError) else True
        await _transition(ctx, job, JobStatus.FAILED, error=_describe(e))
        raise AttemptFailed(_describe(e), retryable, recorded=True) from e

    # 重新讀取鏡頭版本，避免覆寫同一版本另一種工作（關鍵幀／影片）寫入的路徑
    take = await ctx.repos.shots.get_take(job.shot_take_id) or take
    if job.kind == JobKind.KEYFRAME:
        take = replace(take, keyframe_key=key)
    else:
        take = replace(take, clip_key=key)
    await ctx.repos.shots.update_take(take)

    job.actual_cost = result.actual_cost
    await _transition(ctx, job, JobStatus.STORED)
    entry = ctx.budget.record(job.id, JobKind(job.kind), job.model, result.actual_cost, ctx.cost_table)
    if entry is not None:
        await ctx.repos.costs.add(shot.video_id, entry)
    return True
