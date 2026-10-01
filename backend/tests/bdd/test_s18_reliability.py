import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from pydantic import SecretStr
from pytest_bdd import given, scenarios, then, when

from app.api.main import create_app
from app.api.services import AppServices
from app.config import Settings
from app.domain.cost import Budget, CostTable, JobKind
from app.domain.generation import JobStatus
from app.domain.ports import GenerationJob
from app.jobs.generation import GenerationContext, run_generation_job
from app.jobs.recovery import recover
from app.jobs.worker import run_job
from app.providers.webhook import sign
from app.storage import keys
from tests.api_support import ApiEnv
from tests.generation_support import GenEnv
from tests.higgsfield_support import (
    KEYFRAME_KEY,
    RESULT_VIDEO_URL,
    VIDEO_MODEL,
    WEBHOOK_SECRET,
    HfMock,
    hf_mock,
    hf_settings,
)
from tests.orchestration_support import OrchEnv
from tests.reliability_support import GatedProvider, GatedStorage, WorkerCrashed, jobs_of_video

pytestmark = pytest.mark.S18

scenarios("api/s18_reliability.feature")

FALLBACK_KEY = "demo/fallback.mp4"


class Ctx:
    """場景共用狀態；loop 讓同步的步驟函式執行 async 程式碼。"""

    def __init__(self) -> None:
        self.runner = asyncio.Runner()
        self.settings: Settings | None = None
        self.hf: HfMock | None = None
        self.gen: GenEnv | None = None
        self.job: GenerationJob | None = None
        self.api: ApiEnv | None = None
        self.video_id = ""
        self.task: asyncio.Task[None] | None = None
        self.submissions_before = 0
        self.response: dict[str, Any] = {}

    def run(self, coro: Any) -> Any:
        return self.runner.run(coro)


@pytest.fixture
def ctx() -> Iterator[Ctx]:
    c = Ctx()
    yield c
    c.runner.close()


@pytest.fixture
def hf() -> Iterator[HfMock]:
    yield from hf_mock()


# S18-01、S18-02：以 HiggsfieldProvider（respx）執行影片生成工作


@given("WEBHOOK_ENABLED 為 false")
def webhook_disabled(ctx: Ctx, hf: HfMock) -> None:
    ctx.settings = hf_settings(webhook_enabled=False)
    ctx.hf = hf


@given("WEBHOOK_ENABLED 為 true 但 webhook 始終未送達")
def webhook_lost(ctx: Ctx, hf: HfMock) -> None:
    ctx.settings = hf_settings(
        webhook_enabled=True, public_base_url="https://trs.test",
        higgsfield_webhook_secret=SecretStr(WEBHOOK_SECRET),
    )
    ctx.hf = hf  # 只模擬 Higgsfield API；沒有任何請求會打到 /webhooks/higgsfield


@when("執行一個影片生成工作")
def run_video_job(ctx: Ctx) -> None:
    from app.providers.higgsfield import HiggsfieldProvider

    assert ctx.settings is not None and ctx.hf is not None
    ctx.hf.statuses[:] = [{"status": "queued"}, {"status": "in_progress"},
                          {"status": "completed", "video": {"url": RESULT_VIDEO_URL}}]
    gen = GenEnv()
    ctx.gen = gen

    async def go() -> GenerationJob:
        base = await gen.setup()
        await gen.storage.put(KEYFRAME_KEY, b"keyframe-png", "image/png")
        provider = HiggsfieldProvider(ctx.settings, gen.storage)  # type: ignore[arg-type]
        table = CostTable.from_rows([{"kind": "video", "model": VIDEO_MODEL, "credits": "4"}])
        gctx = GenerationContext(
            repos=gen.repos, storage=gen.storage, image_provider=provider, video_provider=provider,
            results=provider, budget=Budget(cap=Decimal("100")), cost_table=table,
            settings=ctx.settings, clock=base.clock, sleep=base.sleep,  # type: ignore[arg-type]
        )
        snapshot = {"shot_no": 1, "keyframe_key": KEYFRAME_KEY, "prompt": "揮手", "duration_s": 5.0}
        return await run_generation_job(gctx, gen.spec(JobKind.VIDEO, snapshot=snapshot))

    ctx.job = ctx.run(go())


@then("工作透過輪詢完成並轉存")
def completed_by_polling(ctx: Ctx) -> None:
    gen, hf, job = ctx.gen, ctx.hf, ctx.job
    assert gen is not None and hf is not None and job is not None and ctx.settings is not None
    assert job.status == JobStatus.STORED
    calls = hf.submit_calls(VIDEO_MODEL)
    assert len(calls) == 1
    hook = calls[0].url.params.get("hf_webhook")
    assert (hook is not None) is ctx.settings.webhook_enabled
    polls = [c for c in hf.router.calls if c.request.url.path.endswith("/status")]
    assert len(polls) == 3
    assert gen.video is not None and gen.take is not None
    clip = keys.clip(gen.video.id, 1, gen.take.attempt)
    assert ctx.run(gen.storage.get(clip)) == b"mp4-bytes"
    assert len(ctx.run(gen.repos.costs.list(gen.video.id))) == 1


# S18-03：webhook 與輪詢同時回報


def _webhook_api(storage: GatedStorage | None = None, provider: GatedProvider | None = None) -> ApiEnv:
    orch_env = OrchEnv(storage=storage or GatedStorage(), provider=provider or GatedProvider())
    env = ApiEnv(orch_env=orch_env)
    services = env.services
    services.settings = services.settings.model_copy(
        update={"higgsfield_webhook_secret": SecretStr(WEBHOOK_SECRET), "public_base_url": "https://trs.test"}
    )
    env._app = create_app(services.settings, services)
    return env


@given("同一個工作的 webhook 與輪詢結果同時到達")
def webhook_and_poll(ctx: Ctx) -> None:
    storage = GatedStorage()
    env = _webhook_api(storage)
    ctx.api = env

    async def go() -> None:
        await env.setup_project()
        ctx.video_id = await env.video_in("generating")
        # 輪詢端取得第 1 鏡關鍵幀的處理權後，轉存停住；此時 Higgsfield 的完成通知到達
        storage.hold(keys.keyframe(ctx.video_id, 1, 1))
        ctx.task = asyncio.create_task(env.run_jobs())
        await storage.waiting.wait()
        job = next(j for j in await jobs_of_video(env.repos, ctx.video_id) if j.status == JobStatus.SUCCEEDED)
        ctx.job = job
        ref = job.provider_idempotency_key or ""
        params = {"ref": ref, "sig": sign(WEBHOOK_SECRET, ref)}
        r = await env.request("POST", "/webhooks/higgsfield", params=params, json={"status": "completed"})
        assert r.status_code == 202

    ctx.run(go())


@when("兩者都被處理")
def both_processed(ctx: Ctx) -> None:
    env = ctx.api
    assert env is not None and ctx.task is not None

    async def go() -> None:
        queued = env.queued("process_webhook")
        assert queued, "webhook 應排入 process_webhook"
        # webhook 觸發的處理在輪詢端轉存途中執行
        await run_job(env.services, "process_webhook", **queued[-1])
        storage = env.orch_env.storage
        assert isinstance(storage, GatedStorage)
        storage.release()
        assert ctx.task is not None
        await ctx.task  # 輪詢端完成，佇列中的 process_webhook 也會再執行一次

    ctx.run(go())


@then("結果只轉存一次")
def stored_once(ctx: Ctx) -> None:
    env, job = ctx.api, ctx.job
    assert env is not None and job is not None
    storage = env.orch_env.storage
    assert isinstance(storage, GatedStorage)
    assert storage.puts[keys.keyframe(ctx.video_id, 1, 1)] == 1
    final = ctx.run(env.repos.jobs.get(job.id))
    assert final is not None and final.status == JobStatus.STORED
    # 影片只推進一次：3 鏡各送出 1 次關鍵幀與 1 次影片，影片進入 review
    assert len(env.orch_env.provider.submissions) == 6
    assert ctx.run(env.status(ctx.video_id)) == "review"


@then("成本帳只記一筆")
def one_cost_entry(ctx: Ctx) -> None:
    env, job = ctx.api, ctx.job
    assert env is not None and job is not None
    entries = ctx.run(env.repos.costs.list(ctx.video_id))
    assert [e.job_id for e in entries].count(job.id) == 1
    assert len(entries) == 6


# S18-04：Worker 重啟


@given('有一個狀態為 "submitted" 的工作')
def submitted_job(ctx: Ctx) -> None:
    provider = GatedProvider()
    env = ApiEnv(orch_env=OrchEnv(provider=provider))
    ctx.api = env

    async def go() -> None:
        await env.setup_project()
        ctx.video_id = await env.video_in("generating")
        provider.crash = True  # Worker 在送出後、第一次查詢時被終止
        with pytest.raises(WorkerCrashed):
            await env.run_jobs()
        jobs = await jobs_of_video(env.repos, ctx.video_id)
        assert jobs and all(j.status == JobStatus.SUBMITTED for j in jobs)
        ctx.submissions_before = len(provider.submissions)
        provider.crash = False

    ctx.run(go())


@when("Worker 重新啟動")
def worker_restart(ctx: Ctx) -> None:
    old = ctx.api
    assert old is not None
    # 新的 Worker：同一個資料庫、儲存與外部供應商，新的編排器與佇列
    orch_env = OrchEnv(provider=old.orch_env.provider, storage=old.orch_env.storage, repos=old.orch_env.repos,
                       bus=old.orch_env.bus, clock=old.orch_env.clock)
    orch_env.project_id = old.orch_env.project_id
    env = ApiEnv(orch_env=orch_env)
    ctx.api = env

    async def go() -> None:
        services: AppServices = env.services
        report = await recover(services.repos, env.queue, services.settings, services.clock)
        assert report.resumed and report.videos == [ctx.video_id]
        await env.run_jobs()

    ctx.run(go())


@then("該工作恢復輪詢並完成")
def resumed_and_done(ctx: Ctx) -> None:
    env = ctx.api
    assert env is not None
    provider = env.orch_env.provider
    assert ctx.submissions_before == 3  # 中止前已送出 3 鏡的關鍵幀
    assert len(provider.submissions) == ctx.submissions_before + 3  # 只新增 3 個影片工作
    first_ids = set(provider.external_ids[: ctx.submissions_before])
    assert first_ids <= set(provider.fetches)
    jobs = ctx.run(jobs_of_video(env.repos, ctx.video_id))
    assert all(j.status == JobStatus.STORED for j in jobs) and len(jobs) == 6
    assert ctx.run(env.status(ctx.video_id)) == "review"


# S18-05：保底成品


@given("已設定保底成品 DEMO_FALLBACK_VIDEO")
def fallback_configured(ctx: Ctx) -> None:
    provider = GatedProvider()
    env = ApiEnv(orch_env=OrchEnv(provider=provider))
    ctx.api = env

    async def go() -> None:
        await env.setup_project()
        await env.orch_env.storage.put(FALLBACK_KEY, b"fallback-mp4", "video/mp4")
        env.services.settings = env.services.settings.model_copy(
            update={"demo_fallback_video": FALLBACK_KEY, "demo_fallback_after_s": 420}
        )

    ctx.run(go())


@given("生成時間超過設定的展示門檻")
def generation_slow(ctx: Ctx) -> None:
    env = ctx.api
    assert env is not None
    provider = env.orch_env.provider
    assert isinstance(provider, GatedProvider)

    async def go() -> None:
        ctx.video_id = await env.video_in("generating")
        provider.gate.clear()  # 供應商遲遲沒有回應
        ctx.task = asyncio.create_task(env.run_jobs())
        for _ in range(50):
            await asyncio.sleep(0)
        env.orch_env.clock.advance(421)

    ctx.run(go())


@when("前端查詢影片狀態")
def query_video(ctx: Ctx) -> None:
    env = ctx.api
    assert env is not None
    r = ctx.run(env.request("GET", f"/videos/{ctx.video_id}"))
    assert r.status_code == 200
    ctx.response = r.json()


@then("回應包含保底成品網址")
def has_fallback(ctx: Ctx) -> None:
    url = ctx.response["fallback_url"]
    assert isinstance(url, str) and FALLBACK_KEY in url
    assert ctx.response["status"] == "generating"
    assert ctx.response["preview_url"] is None


@then("背景生成仍繼續進行")
def generation_continues(ctx: Ctx) -> None:
    env = ctx.api
    assert env is not None and ctx.task is not None
    provider = env.orch_env.provider
    assert isinstance(provider, GatedProvider)

    async def go() -> dict[str, Any]:
        assert ctx.task is not None and not ctx.task.done()
        provider.gate.set()
        await ctx.task
        r = await env.request("GET", f"/videos/{ctx.video_id}")
        return dict(r.json())

    body = ctx.run(go())
    assert body["status"] == "review"
    assert body["preview_url"] and body["fallback_url"] is None
