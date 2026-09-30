"""S06 新增的 repository 方法：記憶體版與資料庫版行為一致（spec 0006 R-008／AC-011）。"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.ports import Repositories
from app.storage.memory_repos import memory_repositories
from app.storage.sql_repos import sql_repositories
from tests.persistence_data import make_job, seed_take

pytestmark = pytest.mark.S06


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
def repos(request: pytest.FixtureRequest) -> Repositories:
    if request.param == "memory":
        return memory_repositories()
    return sql_repositories(request.getfixturevalue("async_engine"))


async def test_r008_job_update_roundtrip(repos: Repositories) -> None:
    take = await seed_take(repos)
    job, _ = await repos.jobs.create_or_get(make_job(take.id, "v1:1:keyframe:abc:1"))

    job.status = "failed"
    job.external_id = "req-123"
    job.provider_idempotency_key = "pk-1"
    job.error = "timeout: 超過 1 秒未完成"
    job.actual_cost = Decimal("1.8")
    job.submitted_at = datetime(2026, 10, 1, 9, 0, 1, 250000, tzinfo=UTC)
    await repos.jobs.update(job)

    assert await repos.jobs.get(job.id) == job
    assert await repos.jobs.get_by_key("v1:1:keyframe:abc:1") == job
    assert await repos.jobs.get_by_key("v1:1:keyframe:abc:2") is None


async def test_r008_saved_job_is_isolated_from_later_mutation(repos: Repositories) -> None:
    take = await seed_take(repos)
    job, _ = await repos.jobs.create_or_get(make_job(take.id, "v1:1:keyframe:abc:1"))

    job.status = "running"

    loaded = await repos.jobs.get(job.id)
    assert loaded is not None and loaded.status == "queued"


async def test_r008_take_update_roundtrip(repos: Repositories) -> None:
    take = await seed_take(repos)

    take.keyframe_key = "videos/v/shots/1/take1/keyframe.png"
    take.clip_key = "videos/v/shots/1/take1/clip.mp4"
    take.status = "done"
    await repos.shots.update_take(take)

    assert await repos.shots.takes(take.shot_id) == [take]
