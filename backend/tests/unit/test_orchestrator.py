"""快速模式編排（spec 0007）。"""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.creative.fake import FakeCreativeEngine
from app.domain.video import InvalidTransition
from app.jobs.events import MemoryEventBus, ProgressEvent
from app.jobs.orchestrator import PlanningFailed
from app.providers.fake import FakeProvider
from tests.orchestration_support import OrchEnv

pytestmark = pytest.mark.S07


async def test_r004_event_has_type_video_id_shot_no_at() -> None:
    bus = MemoryEventBus()
    at = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

    await bus.publish(ProgressEvent("shot_started", "v1", at, shot_no=2))
    await bus.publish(ProgressEvent("render_started", "v1", at))

    first, second = bus.events
    assert (first.type, first.video_id, first.shot_no, first.at) == ("shot_started", "v1", 2, at)
    assert second.shot_no is None


@pytest.mark.parametrize("engine_kw", [{"fail": True}, {"plan_count": 1}, {"plan_count": 4}])
async def test_r001_planning_problem_marks_failed(engine_kw: dict[str, Any]) -> None:
    env = OrchEnv(engine=FakeCreativeEngine(**engine_kw))

    with pytest.raises(PlanningFailed) as exc:
        await env.to_plan_ready()

    assert await env.video_status(exc.value.video_id) == "failed"
    assert "planning_failed" in env.event_types()
    assert await env.repos.plans.list(exc.value.video_id) == []


async def test_r001_plan_context_uses_project_assets() -> None:
    env = OrchEnv()
    await env.to_plan_ready("清晨採梅體驗")

    (ctx,) = env.engine.contexts
    brand = await env.repos.projects.get(env.project_id)
    assert brand is not None and ctx.brand == brand[1]
    assert len(ctx.scene_photos) == 3


async def test_r002_approve_plan_creates_shots_with_adjusted_placement() -> None:
    env = OrchEnv()
    video_id = await env.to_plan_ready()
    moved = {"x": 0.3, "y": 0.9, "scale": 0.5, "flip": True}

    await env.approve_first_plan(video_id, placements={2: moved})

    shots = await env.shots(video_id)
    assert [s.shot_no for s, _ in shots] == [1, 2, 3]
    assert shots[1][0].placement == moved
    assert all(take is not None and take.attempt == 1 for _, take in shots)
    assert await env.video_status(video_id) == "generating"
    # 核准涵蓋調整後的擺放：生成時不會被判定為核准失效
    await env.orch.generate(video_id)
    assert await env.video_status(video_id) == "review"


async def test_r005_completed_shots_kept_on_partial_failure() -> None:
    env = OrchEnv(provider=FakeProvider(outcomes_by_shot={2: ("fail",)}))
    video_id = await env.to_plan_ready()
    await env.approve_first_plan(video_id)

    await env.orch.generate(video_id)

    assert await env.shot_done(video_id, 1)
    assert await env.shot_done(video_id, 3)
    assert not await env.shot_done(video_id, 2)
    assert len(await env.repos.costs.list(video_id)) == 4  # 第 1、3 鏡各 2 個工作
    assert await env.repos.renders.list(video_id) == []


async def test_r005_two_failed_shots_single_needs_attention() -> None:
    env = OrchEnv(provider=FakeProvider(outcomes_by_shot={1: ("fail",), 2: ("fail",)}))
    video_id = await env.to_plan_ready()
    await env.approve_first_plan(video_id)

    await env.orch.generate(video_id)

    trail = await env.status_trail(video_id)
    assert trail.count("needs_attention") == 1
    assert trail[-1] == "needs_attention"
    assert await env.shot_done(video_id, 3)


async def test_r006_regenerate_keeps_other_current_takes() -> None:
    env = OrchEnv()
    video_id = await env.to_review()
    before = {s.shot_no: t for s, t in await env.shots(video_id)}

    await env.orch.regenerate_shot(video_id, 1)

    after = {s.shot_no: t for s, t in await env.shots(video_id)}
    assert after[2] == before[2] and after[3] == before[3]
    assert after[1] is not None and before[1] is not None
    assert after[1].id != before[1].id and after[1].attempt == 2
    assert await env.video_status(video_id) == "review"


async def test_r006_regenerate_requires_review() -> None:
    env = OrchEnv()
    video_id = await env.to_plan_ready()

    with pytest.raises(InvalidTransition):
        await env.orch.regenerate_shot(video_id, 1)


async def test_r007_final_approval_hashes_latest_timeline() -> None:
    env = OrchEnv()
    video_id = await env.to_review()

    approval = await env.orch.approve_final(video_id, "店長")

    assert approval.kind == "final" and approval.approved_by == "店長" and not approval.auto_approved
    assert await env.video_status(video_id) == "approved"
    assert "approved" in env.event_types()
