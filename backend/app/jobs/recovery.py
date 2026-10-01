"""Demo 可靠性（spec 0018）：webhook 觸發的結果處理與 Worker 啟動時的恢復掃描。"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal

from app.config import Settings
from app.domain.cost import Budget
from app.domain.generation import JobStatus, advance, timed_out
from app.domain.ports import GenerationJob, Repositories
from app.domain.video import VideoStatus
from app.jobs.generation import AttemptFailed, GenerationContext, complete_job
from app.jobs.orchestrator import OrchestratorDeps
from app.jobs.queue import JobQueue
from app.providers.base import ProviderError, ProviderJob

log = logging.getLogger(__name__)

IN_FLIGHT = (JobStatus.SUBMITTED, JobStatus.RUNNING)
UNFINISHED = (*IN_FLIGHT, JobStatus.SUCCEEDED)  # webhook 會處理的狀態；succeeded 由條件更新去重


@dataclass
class RecoveryReport:
    resumed: list[str] = field(default_factory=list)  # 接續輪詢的工作
    failed: list[str] = field(default_factory=list)  # 逾時或轉存中斷，標記為失敗的工作
    videos: list[str] = field(default_factory=list)  # 排入 generate_video 的影片


async def video_of(repos: Repositories, job: GenerationJob) -> str | None:
    """工作 → 鏡頭版本 → 鏡頭 → 影片。"""
    take = await repos.shots.get_take(job.shot_take_id)
    shot = await repos.shots.get_shot(take.shot_id) if take is not None else None
    return shot.video_id if shot is not None else None


async def process_webhook(deps: OrchestratorDeps, job_id: str) -> str:
    """webhook 觸發：向供應商查詢狀態（不採用通知內容），成功時以共用的結果處理轉存。

    回傳 skipped（工作已結束）、running／failed（供應商狀態；失敗與重試只由輪詢端決定）、
    processed（由本次轉存）、taken（其他來源已取得處理權）、error（查詢失敗）。
    """
    job = await deps.repos.jobs.get(job_id)
    if job is None or job.status not in UNFINISHED:
        return "skipped"
    try:
        result = await deps.results.fetch_result(
            ProviderJob(job.provider, job.model, job.external_id or "", job.est_cost)
        )
    except ProviderError as e:
        log.warning("webhook 查詢工作 %s 失敗：%s", job_id, type(e).__name__)
        return "error"
    if result.state != "succeeded":
        return result.state
    video_id = await video_of(deps.repos, job)
    video = await deps.repos.videos.get(video_id) if video_id else None
    if video is None:
        return "skipped"
    ctx = GenerationContext(
        repos=deps.repos, storage=deps.storage, image_provider=deps.image_provider,
        video_provider=deps.video_provider, results=deps.results,
        budget=Budget(cap=video.cost_cap or Decimal(0), entries=list(await deps.repos.costs.list(video.id))),
        cost_table=deps.cost_table, settings=deps.settings, clock=deps.clock, sleep=deps.sleep,
    )
    try:
        processed = await complete_job(ctx, job, result)
    except AttemptFailed as e:
        log.warning("webhook 轉存工作 %s 失敗：%s", job_id, e.message)
        return "failed"
    outcome = "processed" if processed else "taken"
    log.info("webhook 處理工作 %s：%s", job_id, outcome)
    return outcome


async def _mark_failed(repos: Repositories, job: GenerationJob, error: str) -> bool:
    failed = replace(job)
    advance(failed, JobStatus.FAILED, error=error)
    return await repos.jobs.update_if(failed, job.status)


async def recover(
    repos: Repositories, queue: JobQueue, settings: Settings, clock: Callable[[], datetime]
) -> RecoveryReport:
    """Worker 啟動時接續進行中的工作（spec 0018 R-005）。

    未逾時的 submitted／running 工作保持原狀，由重新排入的 generate_video 以原 request ID 繼續輪詢；
    逾時的標記為 failed（timeout），停在 succeeded 的標記為 failed（interrupted），兩者都依 S06 規則重試。
    """
    report = RecoveryReport()
    now = clock()
    for job in await repos.jobs.list_by_status(UNFINISHED):
        if job.status == JobStatus.SUCCEEDED:
            if await _mark_failed(repos, job, "interrupted: 轉存途中中斷"):
                report.failed.append(job.id)
        elif timed_out(job.submitted_at or now, now, settings.generation_timeout_s):
            message = f"timeout: 送出後超過 {settings.generation_timeout_s:g} 秒未完成"
            if await _mark_failed(repos, job, message):
                report.failed.append(job.id)
        else:
            report.resumed.append(job.id)
        video_id = await video_of(repos, job)
        video = await repos.videos.get(video_id) if video_id else None
        resumable = video is not None and video.video.status == VideoStatus.GENERATING
        if video is not None and resumable and video.id not in report.videos:
            report.videos.append(video.id)
    for video_id in report.videos:
        await queue.enqueue("generate_video", video_id=video_id)
    log.info("恢復掃描：接續 %d、標記失敗 %d、影片 %d", len(report.resumed), len(report.failed),
             len(report.videos))
    return report

