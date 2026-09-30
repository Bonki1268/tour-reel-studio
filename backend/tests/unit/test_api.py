"""REST API（spec 0008）。"""

from decimal import Decimal

import pytest

from app.api.errors import CostCapTooLow, IdempotencyConflict, InvalidState, error_response
from app.domain.approval import ApprovalInvalidated, ApprovalKind
from app.domain.cost import BudgetExceeded
from app.domain.video import InvalidTransition, VideoEvent, VideoStatus, check_transition
from app.jobs.orchestrator import NotFound
from tests.api_support import ApiEnv

pytestmark = pytest.mark.S08


@pytest.fixture
async def env() -> ApiEnv:
    e = ApiEnv()
    await e.setup_project()
    return e


# 例外對應


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (InvalidTransition(VideoStatus.GENERATING, VideoEvent.REGENERATE_PLANS), 409, "invalid_state"),
        (InvalidState("尚未確認成品"), 409, "invalid_state"),
        (ApprovalInvalidated(ApprovalKind.PLAN, "a" * 64, "b" * 64), 409, "approval_invalidated"),
        (BudgetExceeded(Decimal("10"), Decimal("8"), Decimal("4")), 409, "budget_exceeded"),
        (NotFound("影片不存在"), 404, "not_found"),
        (IdempotencyConflict("內容不同"), 422, "idempotency_conflict"),
        (CostCapTooLow("上限過低"), 422, "cost_cap_too_low"),
    ],
)
def test_r005_exception_mapping(exc: Exception, status: int, code: str) -> None:
    got_status, body = error_response(exc)
    assert (got_status, body["code"]) == (status, code)
    assert body["message"]
    if code == "budget_exceeded":
        assert body["requires_reconfirmation"] is True
        assert (body["cap"], body["committed"], body["requested"]) == ("10", "8", "4")


def test_r005_check_transition_does_not_mutate() -> None:
    assert check_transition(VideoStatus.PLAN_READY, VideoEvent.REGENERATE_PLANS) == VideoStatus.PLANNING
    with pytest.raises(InvalidTransition):
        check_transition(VideoStatus.GENERATING, VideoEvent.REGENERATE_PLANS)


async def test_r005_unknown_video_is_404(env: ApiEnv) -> None:
    r = await env.request("GET", "/videos/00000000-0000-0000-0000-000000000000")
    assert (r.status_code, r.json()["code"]) == (404, "not_found")


# 建立影片


@pytest.mark.parametrize("topic", ["", "   ", "梅" * 201])
async def test_r001_topic_validation(env: ApiEnv, topic: str) -> None:
    r = await env.request("POST", f"/projects/{env.orch_env.project_id}/videos", json={"topic": topic})
    assert r.status_code == 422
    assert env.queue.jobs == []


async def test_r001_unknown_project_is_404(env: ApiEnv) -> None:
    r = await env.request("POST", "/projects/nope/videos", json={"topic": "清晨採梅體驗"})
    assert r.status_code == 404
    assert env.queue.jobs == []


async def test_r002_project_endpoint(env: ApiEnv) -> None:
    r = await env.request("GET", f"/projects/{env.orch_env.project_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "梅子農場"
    assert body["brand"]["tone"] == "溫暖、在地"
    assert body["character"]["anchor_card"]["name"] == "梅子阿伯"
    assert [p["description"] for p in body["scene_photos"]] == ["梅園入口", "採梅步道", "梅子醋工坊"]


# approve-plan：驗證與冪等


async def test_r004_same_key_different_body_is_422(env: ApiEnv) -> None:
    video_id = await env.video_in("plan_ready")
    body = await env.first_plan_body(video_id)
    first = await env.approve_plan(video_id, key="k")
    second = await env.approve_plan(video_id, key="k", cost_cap=str(Decimal(body["cost_cap"]) + 1))

    assert first.status_code == 202
    assert (second.status_code, second.json()["code"]) == (422, "idempotency_conflict")
    assert len(env.queued("generate_video")) == 1


async def test_r004_missing_key_is_422(env: ApiEnv) -> None:
    video_id = await env.video_in("plan_ready")
    body = await env.first_plan_body(video_id)

    r = await env.request("POST", f"/videos/{video_id}/approve-plan", json=body)

    assert r.status_code == 422
    assert await env.status(video_id) == "plan_ready"


async def test_r004_failed_request_not_saved(env: ApiEnv) -> None:
    video_id = await env.video_in("plan_ready")

    low = await env.approve_plan(video_id, key="k", cost_cap="0.5")
    ok = await env.approve_plan(video_id, key="k")

    assert (low.status_code, low.json()["code"]) == (422, "cost_cap_too_low")
    assert ok.status_code == 202


async def test_r003_cost_cap_below_estimate_is_422(env: ApiEnv) -> None:
    video_id = await env.video_in("plan_ready")
    total = Decimal((await env.request("GET", f"/videos/{video_id}")).json()["plans"][0]["estimate"]["total"])

    below = await env.approve_plan(video_id, key="a", cost_cap=str(total - Decimal("0.01")))
    exact = await env.approve_plan(video_id, key="b", cost_cap=str(total))

    assert below.status_code == 422
    assert exact.status_code == 202


@pytest.mark.parametrize(
    "placement",
    [
        {"x": 1.2, "y": 0.5, "scale": 0.4},
        {"x": 0.5, "y": -0.1, "scale": 0.4},
        {"x": 0.5, "y": 0.5, "scale": 0},
    ],
)
async def test_r003_placement_out_of_range_is_422(env: ApiEnv, placement: dict[str, float]) -> None:
    video_id = await env.video_in("plan_ready")

    r = await env.approve_plan(video_id, placements={"2": placement})

    assert r.status_code == 422
    assert await env.status(video_id) == "plan_ready"


async def test_r003_adjusted_placement_is_applied(env: ApiEnv) -> None:
    video_id = await env.video_in("plan_ready")
    moved = {"x": 0.3, "y": 0.9, "scale": 0.5, "flip": True}

    r = await env.approve_plan(video_id, placements={"2": moved})

    assert r.status_code == 202
    shot2 = next(s for s in r.json()["shots"] if s["shot_no"] == 2)
    assert shot2["placement"] == moved


# 其他端點


async def test_r008_regenerate_plans_in_plan_ready(env: ApiEnv) -> None:
    video_id = await env.video_in("plan_ready")

    r = await env.request("POST", f"/videos/{video_id}/plans/regenerate")

    assert r.status_code == 202
    assert env.queued("regenerate_plans") == [{"video_id": video_id}]
    await env.run_jobs()
    assert await env.status(video_id) == "plan_ready"


async def test_r008_regenerate_shot_enqueues(env: ApiEnv) -> None:
    video_id = await env.video_in("review")

    r = await env.request("POST", f"/videos/{video_id}/shots/3/regenerate")

    assert r.status_code == 202
    assert env.queued("regenerate_shot") == [{"video_id": video_id, "shot_no": 3}]
    await env.run_jobs()
    assert await env.status(video_id) == "review"
    assert len(await env.repos.renders.list(video_id)) == 2


async def test_r008_regenerate_unknown_shot_is_404(env: ApiEnv) -> None:
    video_id = await env.video_in("review")
    r = await env.request("POST", f"/videos/{video_id}/shots/9/regenerate")
    assert r.status_code == 404
    assert env.queued("regenerate_shot") == []


async def test_r008_approve_final(env: ApiEnv) -> None:
    video_id = await env.video_in("review")

    r = await env.request("POST", f"/videos/{video_id}/approve")

    assert (r.status_code, r.json()["status"]) == (200, "approved")
    again = await env.request("POST", f"/videos/{video_id}/approve")
    assert again.status_code == 409


async def test_r007_download_requires_approved(env: ApiEnv) -> None:
    video_id = await env.video_in("review")
    r = await env.request("GET", f"/videos/{video_id}/download")
    assert (r.status_code, r.json()["code"]) == (409, "invalid_state")
