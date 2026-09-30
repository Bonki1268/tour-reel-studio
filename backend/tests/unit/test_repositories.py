"""Repository 行為測試：同一組測試分別對記憶體版與資料庫版執行（spec 0005 R-006／AC-007）。"""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, inspect, text

from alembic import command
from app.domain.approval import Approval, ApprovalKind
from app.domain.cost import CostEntry
from app.domain.ports import Repositories
from app.domain.video import Video, VideoEvent
from app.storage.memory_repos import memory_repositories
from app.storage.sql_repos import sql_repositories
from tests.conftest import alembic_config
from tests.persistence_data import (
    SECTION7_TABLES,
    assert_same_json,
    make_job,
    sample_placement,
    sample_project,
    sample_timeline,
    seed_shot,
    seed_take,
    seed_video,
)

pytestmark = pytest.mark.S05


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
def repos(request: pytest.FixtureRequest) -> Repositories:
    if request.param == "memory":
        return memory_repositories()
    return sql_repositories(request.getfixturevalue("async_engine"))


def fixed_clock(start: datetime) -> "Iterator[datetime]":
    t = start
    while True:
        yield t
        t += timedelta(minutes=1, microseconds=123)


async def test_r002_project_and_brand_roundtrip(repos: Repositories) -> None:
    project, brand = sample_project()
    await repos.projects.add(project, brand)

    loaded = await repos.projects.get(project.id)

    assert loaded is not None
    assert loaded == (project, brand)
    assert_same_json(loaded[1].visual, brand.visual)
    assert_same_json(loaded[1].selling_points, brand.selling_points)
    assert_same_json(loaded[1].info, brand.info)
    assert await repos.projects.get("00000000-0000-0000-0000-000000000000") is None


async def test_r003_takes_are_kept(repos: Repositories) -> None:
    shot = await seed_shot(repos)
    first = await repos.shots.add_take(
        shot.id, keyframe_key="videos/v/shots/1/take1/keyframe.png", status="done"
    )

    second = await repos.shots.add_take(shot.id)

    takes = await repos.shots.takes(shot.id)
    assert [t.attempt for t in takes] == [1, 2]
    assert takes[0] == first
    assert takes[1] == second
    reloaded = await repos.shots.get_shot(shot.id)
    assert reloaded is not None
    assert reloaded.current_take_id == second.id


async def test_r004_create_or_get_returns_existing(repos: Repositories) -> None:
    take = await seed_take(repos)
    original, created = await repos.jobs.create_or_get(make_job(take.id, "v1:1:keyframe:abc:1"))
    assert created is True

    duplicate = make_job(take.id, "v1:1:keyframe:abc:1", model="img-model-b", est_cost=Decimal("9"))
    returned, created_again = await repos.jobs.create_or_get(duplicate)

    assert created_again is False
    assert returned == original
    assert await repos.jobs.count_by_key("v1:1:keyframe:abc:1") == 1
    assert await repos.jobs.get(duplicate.id) is None
    assert await repos.jobs.get(original.id) == original


async def test_r005_json_types_roundtrip(repos: Repositories) -> None:
    video = await seed_video(repos, timeline=sample_timeline())
    shot = await seed_shot(repos, placement=sample_placement(), prompt={"text": "晨光", "weights": [0.5, 1]})

    loaded_video = await repos.videos.get(video.id)
    loaded_shot = await repos.shots.get_shot(shot.id)

    assert loaded_video is not None and loaded_shot is not None
    assert_same_json(loaded_video.timeline, sample_timeline())
    assert_same_json(loaded_shot.placement, sample_placement())
    assert_same_json(loaded_shot.prompt, {"text": "晨光", "weights": [0.5, 1]})


async def test_r005_saved_json_is_isolated_from_later_mutation(repos: Repositories) -> None:
    timeline = sample_timeline()
    video = await seed_video(repos, timeline=timeline)

    timeline["tracks"].append({"type": "extra"})
    video.topic = "改過的主題"

    loaded = await repos.videos.get(video.id)
    assert loaded is not None
    assert_same_json(loaded.timeline, sample_timeline())
    assert loaded.topic == "梅子季限定"


async def test_r007_video_history_approvals_costs_roundtrip(repos: Repositories) -> None:
    ticks = fixed_clock(datetime(2026, 10, 1, 1, 2, 3, 456789, tzinfo=UTC))
    record = await seed_video(repos, video=Video(clock=lambda: next(ticks)))
    record.video.apply(VideoEvent.SUBMIT_TOPIC)
    record.video.apply(VideoEvent.PLANS_READY)
    record.cost_cap = Decimal("12.5")
    record.timeline = sample_timeline()
    await repos.videos.save(record)

    loaded = await repos.videos.get(record.id)

    assert loaded is not None
    assert loaded.video.status == record.video.status
    assert loaded.video.history == record.video.history
    assert loaded.cost_cap == Decimal("12.5")
    assert replace(loaded, video=record.video) == record

    approvals = [
        Approval(ApprovalKind.PLAN, "h" * 64, Decimal("12.5"), False, "店長", next(ticks)),
        Approval(ApprovalKind.KEYFRAMES, "k" * 64, None, True, None, next(ticks)),
    ]
    for a in approvals:
        await repos.approvals.add(record.id, a)
    entries = [CostEntry("job-1", Decimal("1.2345"), "provider"), CostEntry("job-2", Decimal("3"), "table")]
    for e in entries:
        await repos.costs.add(record.id, e)

    assert await repos.approvals.list(record.id) == approvals
    loaded_entries = await repos.costs.list(record.id)
    assert loaded_entries == entries
    assert all(isinstance(e.credits, Decimal) for e in loaded_entries)
    assert await repos.approvals.list("00000000-0000-0000-0000-000000000000") == []


@pytest.mark.integration
def test_r001_migrations_downgrade_to_base(sync_engine: Engine) -> None:
    schema = "s05_downgrade"
    with sync_engine.connect() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.commit()
        try:
            command.upgrade(alembic_config(conn), "head")
            conn.commit()
            assert SECTION7_TABLES <= set(inspect(conn).get_table_names(schema=schema))

            command.downgrade(alembic_config(conn), "base")
            conn.commit()
            remaining = set(inspect(conn).get_table_names(schema=schema)) - {"alembic_version"}
            assert remaining == set()
        finally:
            conn.rollback()
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("RESET search_path"))  # 連線會回到連線池，不可殘留 search_path
            conn.commit()
