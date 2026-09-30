"""S08 冪等鍵 repository 與 Redis 整合（spec 0008 R-004、R-009）。"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from app.api.services import AppServices
from app.config import load_settings
from app.domain.ports import IdempotencyRecord, Repositories
from app.jobs.events import ProgressEvent, RedisEventBus
from app.jobs.queue import ArqJobQueue
from app.jobs.worker import arq_functions
from app.storage.memory_repos import memory_repositories
from app.storage.sql_repos import sql_repositories
from tests.api_support import ApiEnv

pytestmark = pytest.mark.S08


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
def repos(request: pytest.FixtureRequest) -> Repositories:
    if request.param == "memory":
        return memory_repositories()
    return sql_repositories(request.getfixturevalue("async_engine"))


async def test_r009_idempotency_repo_roundtrip(repos: Repositories) -> None:
    record = IdempotencyRecord("approve-plan:v1:k", "h" * 64, 202, {"id": "v1", "status": "generating"})

    assert await repos.idempotency.get(record.key) is None
    assert await repos.idempotency.save(record) is True
    assert await repos.idempotency.save(IdempotencyRecord(record.key, "x" * 64, 202, {})) is False
    assert await repos.idempotency.get(record.key) == record


def _redis_url() -> str:
    return load_settings(env_file=None).redis_url


@pytest.mark.integration
async def test_r009_redis_event_bus_pubsub() -> None:
    publisher, subscriber = RedisEventBus(_redis_url()), RedisEventBus(_redis_url())
    video_id = str(uuid.uuid4())
    event = ProgressEvent("plan_ready", video_id, datetime(2026, 10, 1, 9, 0, tzinfo=UTC), None, {"n": 1})
    try:
        async with subscriber.subscribe(video_id) as events:
            await publisher.publish(ProgressEvent("other", str(uuid.uuid4()), event.at))
            await publisher.publish(event)
            assert await asyncio.wait_for(anext(events), 5) == event
    finally:
        await publisher.close()
        await subscriber.close()


@pytest.mark.integration
async def test_r009_arq_worker_runs_plan_job() -> None:
    from arq.connections import RedisSettings
    from arq.worker import Worker

    env = ApiEnv()
    await env.setup_project()
    services: AppServices = env.services
    queue_name = f"trs-test:{uuid.uuid4()}"
    services.queue = ArqJobQueue(_redis_url(), queue_name=queue_name)
    video = await services.orchestrator.create_video(env.orch_env.project_id, "清晨採梅體驗")

    await services.queue.enqueue("plan_video", video_id=video.id)

    async def startup(ctx: dict[str, object]) -> None:
        ctx["services"] = services

    worker = Worker(
        functions=arq_functions(), redis_settings=RedisSettings.from_dsn(_redis_url()),
        queue_name=queue_name, burst=True, on_startup=startup, poll_delay=0.05, handle_signals=False,
    )
    try:
        await worker.main()
    finally:
        await worker.close()
        assert isinstance(services.queue, ArqJobQueue)
        await services.queue.close()
    assert worker.jobs_complete == 1 and worker.jobs_failed == 0
    assert await env.status(video.id) == "plan_ready"
