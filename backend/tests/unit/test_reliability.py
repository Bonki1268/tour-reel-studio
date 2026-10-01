import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.main import create_app
from app.config import Settings
from app.domain.cost import Budget, JobKind
from app.domain.fallback import fallback_due
from app.domain.generation import JobStatus
from app.domain.ports import GenerationJob, Render, Repositories
from app.domain.video import Video, VideoEvent, VideoStatus
from app.jobs.generation import build_attempt, complete_job, run_generation_job
from app.jobs.queue import MemoryJobQueue
from app.jobs.recovery import process_webhook, recover
from app.providers.base import ProviderRequest, ProviderResult
from app.providers.fake import FakeProvider
from app.providers.webhook import sign
from app.storage import keys
from app.storage.memory_repos import memory_repositories
from app.storage.sql_repos import sql_repositories
from tests.api_support import ApiEnv
from tests.generation_support import FakeClock, GenEnv, keyframe_key
from tests.persistence_data import make_job, seed_take
from tests.reliability_support import GatedStorage, YieldingClock

pytestmark = pytest.mark.S18

WEBHOOK_SECRET = "whsec-s18"


# R-004 條件更新


async def _two_writers(repos: Repositories) -> tuple[GenerationJob, GenerationJob, GenerationJob]:
    take = await seed_take(repos)
    job, _ = await repos.jobs.create_or_get(make_job(take.id, "s18-k1"))
    a = replace(job, status=JobStatus.SUBMITTED, external_id="req-A")
    b = replace(job, status=JobStatus.FAILED, error="B")
    return job, a, b


async def test_r004_update_if_memory_only_one_wins() -> None:
    repos = memory_repositories()
    job, a, b = await _two_writers(repos)

    results = await asyncio.gather(repos.jobs.update_if(a, JobStatus.QUEUED),
                                   repos.jobs.update_if(b, JobStatus.QUEUED))

    assert sorted(results) == [False, True]
    stored = await repos.jobs.get(job.id)
    winner = a if results[0] else b
    assert stored is not None and stored.status == winner.status and stored.error == winner.error


async def test_r004_update_if_memory_rejects_stale_status() -> None:
    repos = memory_repositories()
    job, a, _ = await _two_writers(repos)
    assert await repos.jobs.update_if(a, JobStatus.RUNNING) is False
    assert (await repos.jobs.get(job.id)).status == JobStatus.QUEUED  # type: ignore[union-attr]


@pytest.fixture
async def sql_repos(async_engine: AsyncEngine) -> AsyncIterator[Repositories]:
    yield sql_repositories(async_engine)


async def test_r004_update_if_sql_only_one_wins(sql_repos: Repositories) -> None:
    job, a, b = await _two_writers(sql_repos)

    results = await asyncio.gather(sql_repos.jobs.update_if(a, JobStatus.QUEUED),
                                   sql_repos.jobs.update_if(b, JobStatus.QUEUED))

    assert sorted(results) == [False, True]
    stored = await sql_repos.jobs.get(job.id)
    winner = a if results[0] else b
    assert stored is not None and stored.status == winner.status
    assert stored.external_id == winner.external_id and stored.error == winner.error


async def test_r004_sql_lookups(sql_repos: Repositories) -> None:
    job, a, _ = await _two_writers(sql_repos)
    assert await sql_repos.jobs.update_if(a, JobStatus.QUEUED)
    found = await sql_repos.jobs.get_by_provider_key(job.provider_idempotency_key or "")
    assert job.provider_idempotency_key is None or (found is not None and found.id == job.id)
    listed = await sql_repos.jobs.list_by_status([JobStatus.SUBMITTED, JobStatus.RUNNING])
    assert [j.id for j in listed] == [job.id]
    take = await sql_repos.shots.get_take(job.shot_take_id)
    assert take is not None and take.id == job.shot_take_id
    assert await sql_repos.shots.get_take("missing") is None


async def test_r004_memory_lookups() -> None:
    repos = memory_repositories()
    take = await seed_take(repos)
    job, _ = await repos.jobs.create_or_get(make_job(take.id, "s18-k2", provider_idempotency_key="pik-9"))
    assert (await repos.jobs.get_by_provider_key("pik-9")).id == job.id  # type: ignore[union-attr]
    assert await repos.jobs.get_by_provider_key("nope") is None
    assert [j.id for j in await repos.jobs.list_by_status([JobStatus.QUEUED])] == [job.id]
    assert await repos.jobs.list_by_status([JobStatus.RUNNING]) == []
    assert (await repos.shots.get_take(take.id)).id == take.id  # type: ignore[union-attr]


# R-004 共用的結果處理


async def _running_keyframe(env: GenEnv) -> GenerationJob:
    """已送出並停在 running 的第 1 次關鍵幀工作（直接寫入，不經過輪詢）。"""
    ctx = await env.setup()
    spec = env.spec(JobKind.KEYFRAME)
    job, _ = await ctx.repos.jobs.create_or_get(build_attempt(ctx, spec, 1))
    pjob = await env.provider.compose(
        ProviderRequest(job.model, spec.input_snapshot, job.provider_idempotency_key or job.id)
    )
    running = replace(job, status=JobStatus.RUNNING, external_id=pjob.external_id, provider=pjob.provider,
                      submitted_at=env.clock())
    assert await ctx.repos.jobs.update_if(running, JobStatus.QUEUED)
    return running


def _succeeded() -> ProviderResult:
    return ProviderResult("succeeded", url="https://fake.example/compose/fake-req-1", actual_cost=None)


async def test_r004_complete_job_concurrent_stores_once() -> None:
    storage = GatedStorage()
    env = GenEnv(storage=storage)
    job = await _running_keyframe(env)
    assert env.ctx is not None
    storage.hold(keyframe_key(env))

    first = asyncio.create_task(complete_job(env.ctx, job, _succeeded()))
    await storage.waiting.wait()
    second = await complete_job(env.ctx, job, _succeeded())  # 另一個來源：處理權已被取得
    storage.release()

    assert second is False and await first is True
    assert storage.puts[keyframe_key(env)] == 1
    assert len(await env.repos.costs.list(env.video.id)) == 1  # type: ignore[union-attr]
    stored = await env.repos.jobs.get(job.id)
    assert stored is not None and stored.status == JobStatus.STORED
    take = (await env.repos.shots.takes(env.shot.id))[0]  # type: ignore[union-attr]
    assert take.keyframe_key == keyframe_key(env)


async def test_r004_poller_defers_to_other_winner() -> None:
    """webhook 先取得處理權並轉存中：輪詢端不重複轉存，等到 stored 後視為完成並同步預算。"""
    storage = GatedStorage()
    env = GenEnv(storage=storage, clock=YieldingClock())
    env.provider._running_polls = 0  # 第一次查詢就完成
    job = await _running_keyframe(env)
    assert env.ctx is not None and env.video is not None
    storage.hold(keyframe_key(env))
    other = replace(env.ctx, budget=Budget(cap=env.cap))  # webhook 端有自己的預算
    webhook = asyncio.create_task(complete_job(other, job, _succeeded()))
    await storage.waiting.wait()

    poller = asyncio.create_task(run_generation_job(env.ctx, env.spec(JobKind.KEYFRAME)))
    for _ in range(20):
        await asyncio.sleep(0)
    storage.release()
    result = await poller
    assert await webhook is True

    assert result.status == JobStatus.STORED and result.id == job.id
    assert storage.puts[keyframe_key(env)] == 1
    assert len(await env.repos.costs.list(env.video.id)) == 1
    assert env.ctx.budget.spent() > 0 and job.id not in env.ctx.budget.reserved


async def test_r004_poller_sees_other_failure_and_retries() -> None:
    """輪詢中的工作被其他來源標記為失敗：輪詢端不覆寫該狀態，直接進行第 2 次嘗試。"""
    env = GenEnv(provider=FakeProvider(["never", "succeed"]), clock=YieldingClock())
    ctx = await env.setup()
    poller = asyncio.create_task(run_generation_job(ctx, env.spec(JobKind.KEYFRAME)))
    first: GenerationJob | None = None
    for _ in range(200):
        await asyncio.sleep(0)
        running = await env.repos.jobs.list_by_status([JobStatus.RUNNING])
        if running:
            first = running[0]
            break
    assert first is not None
    assert await env.repos.jobs.update_if(replace(first, status=JobStatus.FAILED, error="轉存失敗"),
                                          JobStatus.RUNNING)

    result = await poller

    assert result.attempt == 2 and result.status == JobStatus.STORED
    again = await env.repos.jobs.get(first.id)
    assert again is not None and again.status == JobStatus.FAILED and again.error == "轉存失敗"
    assert env.clock() - datetime(2026, 10, 1, 9, 0, tzinfo=UTC) < timedelta(seconds=600)


# R-003 webhook


def _webhook_env() -> ApiEnv:
    env = ApiEnv()
    services = env.services
    services.settings = services.settings.model_copy(
        update={"higgsfield_webhook_secret": SecretStr(WEBHOOK_SECRET), "public_base_url": "https://trs.test"}
    )
    env._app = create_app(services.settings, services)
    return env


async def _generating_video(env: ApiEnv) -> tuple[str, GenerationJob]:
    """第 1 鏡的關鍵幀已送出並停在 running。"""
    env.orch_env.provider._outcomes = ["never"]
    await env.setup_project()
    video_id = await env.video_in("generating")
    env.orch_env.orch.deps.settings = env.orch_env.orch.deps.settings.model_copy(
        update={"generation_timeout_s": 1}
    )
    await env.run_jobs()  # 逾時後各鏡失敗；只為了產生已送出的工作
    jobs = await env.repos.jobs.list_by_status([JobStatus.FAILED, JobStatus.FAILED_FINAL])
    job = replace(jobs[0], status=JobStatus.RUNNING, error=None)
    await env.repos.jobs.update(job)
    return video_id, job


def _hook(env: ApiEnv, ref: str, secret: str = WEBHOOK_SECRET) -> object:
    return env.request("POST", "/webhooks/higgsfield", params={"ref": ref, "sig": sign(secret, ref)},
                       json={"status": "completed"})


async def test_r003_webhook_known_job_enqueues_processing() -> None:
    env = _webhook_env()
    video_id, job = await _generating_video(env)
    before = len(env.queue.jobs)

    r = await _hook(env, job.provider_idempotency_key or "")  # type: ignore[misc]

    assert r.status_code == 202
    assert env.queue.jobs[before:] == [("process_webhook", {"video_id": video_id, "job_id": job.id})]


async def test_r003_webhook_unknown_ref_not_enqueued() -> None:
    env = _webhook_env()
    before = len(env.queue.jobs)
    r = await _hook(env, "unknown-ref")  # type: ignore[misc]
    assert r.status_code == 202
    assert len(env.queue.jobs) == before


async def test_r003_webhook_invalid_signature_not_enqueued() -> None:
    env = _webhook_env()
    _, job = await _generating_video(env)
    before = len(env.queue.jobs)
    r = await _hook(env, job.provider_idempotency_key or "", secret="wrong")  # type: ignore[misc]
    assert r.status_code == 401
    assert len(env.queue.jobs) == before


async def test_r003_webhook_finished_job_not_enqueued() -> None:
    env = _webhook_env()
    _, job = await _generating_video(env)
    await env.repos.jobs.update(replace(job, status=JobStatus.FAILED_FINAL))
    before = len(env.queue.jobs)
    r = await _hook(env, job.provider_idempotency_key or "")  # type: ignore[misc]
    assert r.status_code == 202
    assert len(env.queue.jobs) == before


async def test_r003_process_webhook_skips_stored_job() -> None:
    env = _webhook_env()
    _, job = await _generating_video(env)
    await env.repos.jobs.update(replace(job, status=JobStatus.STORED))
    fetches = len(env.orch_env.provider.fetches)
    puts = dict(env.orch_env.storage._objects)

    outcome = await process_webhook(env.orch_env.orch.deps, job.id)

    assert outcome == "skipped"
    assert len(env.orch_env.provider.fetches) == fetches
    assert env.orch_env.storage._objects == puts


async def test_r003_process_webhook_running_result_changes_nothing() -> None:
    env = _webhook_env()
    _, job = await _generating_video(env)
    outcome = await process_webhook(env.orch_env.orch.deps, job.id)
    assert outcome == "running"
    stored = await env.repos.jobs.get(job.id)
    assert stored is not None and stored.status == JobStatus.RUNNING


async def test_r003_process_webhook_stores_succeeded_result() -> None:
    env = _webhook_env()
    _, job = await _generating_video(env)
    env.orch_env.provider._jobs[job.external_id or ""].outcome = "succeed"
    env.orch_env.provider._running_polls = 0

    outcome = await process_webhook(env.orch_env.orch.deps, job.id)

    assert outcome == "processed"
    stored = await env.repos.jobs.get(job.id)
    assert stored is not None and stored.status == JobStatus.STORED
    take = await env.repos.shots.get_take(job.shot_take_id)
    assert take is not None and take.keyframe_key and await env.orch_env.storage.exists(take.keyframe_key)


# R-005 恢復


async def _recovery_env() -> tuple[ApiEnv, str, list[GenerationJob]]:
    env = ApiEnv()
    env.orch_env.provider._outcomes = ["never"]
    await env.setup_project()
    video_id = await env.video_in("generating")
    env.orch_env.orch.deps.settings = env.orch_env.orch.deps.settings.model_copy(
        update={"generation_timeout_s": 1}
    )
    await env.run_jobs()
    jobs = sorted(await env.repos.jobs.list_by_status([JobStatus.FAILED, JobStatus.FAILED_FINAL]),
                  key=lambda j: j.id)
    # 影片退回 generating（模擬 Worker 中止時的狀態）
    video = await env.repos.videos.get(video_id)
    assert video is not None
    video.video.status = VideoStatus.GENERATING
    await env.repos.videos.save(video)
    return env, video_id, jobs


def _settings(timeout_s: float = 600) -> Settings:
    return Settings(generation_timeout_s=timeout_s)


async def test_r005_recover_resumes_only_fresh_jobs() -> None:
    env, video_id, jobs = await _recovery_env()
    clock = env.orch_env.clock
    fresh = replace(jobs[0], status=JobStatus.SUBMITTED, error=None, submitted_at=clock())
    long_ago = clock() - timedelta(seconds=900)
    stale = replace(jobs[1], status=JobStatus.RUNNING, error=None, submitted_at=long_ago)
    await env.repos.jobs.update(fresh)
    await env.repos.jobs.update(stale)
    queue = MemoryJobQueue()

    report = await recover(env.repos, queue, _settings(600), clock)

    assert report.resumed == [fresh.id]
    assert report.failed == [stale.id]
    stale_now = await env.repos.jobs.get(stale.id)
    assert stale_now is not None and stale_now.status == JobStatus.FAILED
    assert "timeout" in (stale_now.error or "")
    fresh_now = await env.repos.jobs.get(fresh.id)
    assert fresh_now is not None and fresh_now.status == JobStatus.SUBMITTED
    assert queue.jobs == [("generate_video", {"video_id": video_id})]


async def test_r005_recover_marks_succeeded_interrupted() -> None:
    env, _, jobs = await _recovery_env()
    stuck = replace(jobs[0], status=JobStatus.SUCCEEDED, error=None, submitted_at=env.orch_env.clock())
    await env.repos.jobs.update(stuck)

    report = await recover(env.repos, MemoryJobQueue(), _settings(), env.orch_env.clock)

    assert report.failed == [stuck.id]
    now = await env.repos.jobs.get(stuck.id)
    assert now is not None and now.status == JobStatus.FAILED and "interrupted" in (now.error or "")


async def test_r005_recover_enqueues_each_generating_video_once() -> None:
    env, video_id, jobs = await _recovery_env()
    clock = env.orch_env.clock
    for job in jobs[:2]:
        await env.repos.jobs.update(replace(job, status=JobStatus.RUNNING, error=None, submitted_at=clock()))
    queue = MemoryJobQueue()
    await recover(env.repos, queue, _settings(), clock)
    assert queue.jobs == [("generate_video", {"video_id": video_id})]

    video = await env.repos.videos.get(video_id)
    assert video is not None
    video.video.status = VideoStatus.NEEDS_ATTENTION
    await env.repos.videos.save(video)
    queue = MemoryJobQueue()
    report = await recover(env.repos, queue, _settings(), clock)
    assert queue.jobs == [] and report.videos == []


async def test_r005_recover_with_nothing_in_flight() -> None:
    report = await recover(memory_repositories(), MemoryJobQueue(), _settings(), FakeClock())
    assert (report.resumed, report.failed, report.videos) == ([], [], [])


# R-006 保底成品


def _video_generating(clock: FakeClock) -> Video:
    video = Video(clock=clock)
    video.apply(VideoEvent.SUBMIT_TOPIC)
    video.apply(VideoEvent.PLANS_READY)
    clock.advance(60)
    video.apply(VideoEvent.APPROVE_PLAN)
    return video


def test_r006_fallback_due_after_threshold() -> None:
    clock = FakeClock()
    video = _video_generating(clock)
    assert video.status == VideoStatus.GENERATING
    start = clock()
    assert not fallback_due(video, start + timedelta(seconds=419), 420, has_render=False)
    assert fallback_due(video, start + timedelta(seconds=420), 420, has_render=False)
    assert not fallback_due(video, start + timedelta(seconds=999), 420, has_render=True)


def test_r006_fallback_uses_last_generating_entry() -> None:
    clock = FakeClock()
    video = _video_generating(clock)
    video.apply(VideoEvent.SHOT_FAILED_FINAL)  # needs_attention
    assert fallback_due(video, clock() + timedelta(seconds=500), 420, has_render=False)
    clock.advance(500)
    video.apply(VideoEvent.REGENERATE_SHOT)  # 重新進入 generating
    assert video.status == VideoStatus.GENERATING
    assert not fallback_due(video, clock() + timedelta(seconds=100), 420, has_render=False)
    assert fallback_due(video, clock() + timedelta(seconds=420), 420, has_render=False)


def test_r006_fallback_not_due_in_other_statuses() -> None:
    clock = FakeClock()
    video = Video(clock=clock)
    video.apply(VideoEvent.SUBMIT_TOPIC)
    assert not fallback_due(video, clock() + timedelta(days=1), 420, has_render=False)


def test_r006_fallback_settings_default() -> None:
    s = Settings()
    assert s.demo_fallback_video == "" and s.demo_fallback_after_s == 420


async def _fallback_env(**settings: object) -> tuple[ApiEnv, str]:
    env = ApiEnv()
    env.orch_env.provider._outcomes = ["never"]
    await env.setup_project()
    video_id = await env.video_in("generating")
    env.services.settings = env.services.settings.model_copy(update=settings)
    env._app = None
    return env, video_id


async def _fallback_url(env: ApiEnv, video_id: str) -> object:
    r = await env.request("GET", f"/videos/{video_id}")
    assert r.status_code == 200
    return r.json()["fallback_url"]


async def test_r006_fallback_url_null_cases() -> None:
    key = "demo/fallback.mp4"
    env, video_id = await _fallback_env(demo_fallback_video=key, demo_fallback_after_s=420)
    assert await _fallback_url(env, video_id) is None  # 門檻前
    env.orch_env.clock.advance(421)
    assert await _fallback_url(env, video_id) is None  # 物件不存在
    await env.orch_env.storage.put(key, b"mp4", "video/mp4")
    url = await _fallback_url(env, video_id)
    assert isinstance(url, str) and key in url

    env.services.settings = env.services.settings.model_copy(update={"demo_fallback_video": ""})
    env._app = None
    assert await _fallback_url(env, video_id) is None  # 未設定

    env.services.settings = env.services.settings.model_copy(update={"demo_fallback_video": key})
    env._app = None
    await env.repos.renders.add(Render("r1", video_id, "9:16", keys.render(video_id, "r1")))
    await env.orch_env.storage.put(keys.render(video_id, "r1"), b"mp4", "video/mp4")
    assert await _fallback_url(env, video_id) is None  # 已有成品


async def test_r006_fallback_not_in_review() -> None:
    env = ApiEnv()
    await env.setup_project()
    video_id = await env.video_in("review")
    await env.orch_env.storage.put("demo/fallback.mp4", b"mp4", "video/mp4")
    env.services.settings = env.services.settings.model_copy(
        update={"demo_fallback_video": "demo/fallback.mp4", "demo_fallback_after_s": 1}
    )
    env._app = None
    env.orch_env.clock.advance(3600)
    assert await _fallback_url(env, video_id) is None
