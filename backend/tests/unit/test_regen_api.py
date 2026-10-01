"""重生所需點數與提高成本上限（spec 0016 R-007）。"""

from decimal import Decimal

import pytest

from app.domain.approval import ApprovalKind, raise_cap
from tests.api_support import ApiEnv, as_decimal
from tests.generation_support import KEYFRAME_PRICE, VIDEO_PRICE

pytestmark = pytest.mark.S16

SHOT_COST = KEYFRAME_PRICE + VIDEO_PRICE


@pytest.fixture
async def env() -> ApiEnv:
    env = ApiEnv()
    await env.setup_project()
    return env


async def test_r007_regen_cost_in_video(env: ApiEnv) -> None:
    video_id = await env.video_in("review")
    shots = (await env.request("GET", f"/videos/{video_id}")).json()["shots"]
    assert len(shots) == 3
    assert all(as_decimal(s["regen_cost"]) == SHOT_COST for s in shots)


async def test_r007_raise_cap_records_approval(env: ApiEnv) -> None:
    video_id = await env.video_in("review")
    before = (await env.request("GET", f"/videos/{video_id}")).json()
    new_cap = as_decimal(before["cost_cap"]) + Decimal("10")
    r = await env.request("POST", f"/videos/{video_id}/shots/3/regenerate", json={"cost_cap": str(new_cap)})
    assert r.status_code == 202
    assert as_decimal(r.json()["cost_cap"]) == new_cap
    approvals = [a for a in await env.repos.approvals.list(video_id) if a.kind == ApprovalKind.PLAN]
    assert len(approvals) == 2
    assert approvals[-1].cost_cap == new_cap
    assert approvals[-1].input_hash == approvals[0].input_hash
    assert approvals[-1].approved_by and not approvals[-1].auto_approved
    assert env.queued("regenerate_shot") == [{"video_id": video_id, "shot_no": 3}]


@pytest.mark.parametrize("delta", [Decimal("0"), Decimal("-1")])
async def test_r007_cap_not_raised_is_422(env: ApiEnv, delta: Decimal) -> None:
    video_id = await env.video_in("review")
    cap = as_decimal((await env.request("GET", f"/videos/{video_id}")).json()["cost_cap"])
    r = await env.request(
        "POST", f"/videos/{video_id}/shots/3/regenerate", json={"cost_cap": str(cap + delta)}
    )
    assert r.status_code == 422
    assert r.json()["code"] == "cap_not_raised"
    assert env.queued("regenerate_shot") == []
    assert len([a for a in await env.repos.approvals.list(video_id) if a.kind == ApprovalKind.PLAN]) == 1


async def test_r007_without_body_unchanged(env: ApiEnv) -> None:
    video_id = await env.video_in("review")
    cap = (await env.request("GET", f"/videos/{video_id}")).json()["cost_cap"]
    r = await env.request("POST", f"/videos/{video_id}/shots/2/regenerate")
    assert r.status_code == 202
    assert r.json()["cost_cap"] == cap
    assert env.queued("regenerate_shot") == [{"video_id": video_id, "shot_no": 2}]


async def test_r007_raised_cap_used_for_budget(env: ApiEnv) -> None:
    video_id = await env.video_in("review")
    cap = as_decimal((await env.request("GET", f"/videos/{video_id}")).json()["cost_cap"])
    # 第一次重生用掉預留的單鏡額度
    assert (await env.request("POST", f"/videos/{video_id}/shots/1/regenerate")).status_code == 202
    await env.run_jobs()
    assert await env.status(video_id) == "review"
    # 再重生一鏡會超出原上限；使用者同意提高後應以新上限完成
    new_cap = cap + SHOT_COST
    r = await env.request("POST", f"/videos/{video_id}/shots/2/regenerate", json={"cost_cap": str(new_cap)})
    assert r.status_code == 202
    await env.run_jobs()
    assert await env.status(video_id) == "review"
    spent = as_decimal((await env.request("GET", f"/videos/{video_id}")).json()["spent"])
    assert spent > cap
    assert spent <= new_cap


def test_r007_raise_cap_domain() -> None:
    from datetime import UTC, datetime

    from app.domain.approval import Approval

    previous = Approval(
        ApprovalKind.PLAN, "hash-1", Decimal("40"), False, "店長", datetime(2026, 10, 1, tzinfo=UTC)
    )
    raised = raise_cap(previous, Decimal("75"), "店長")
    assert (raised.kind, raised.input_hash, raised.cost_cap) == (ApprovalKind.PLAN, "hash-1", Decimal("75"))
    assert raised.approved_at >= previous.approved_at
    with pytest.raises(ValueError):
        raise_cap(previous, Decimal("40"), "店長")
