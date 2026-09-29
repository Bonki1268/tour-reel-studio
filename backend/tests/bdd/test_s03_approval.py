import copy
from decimal import Decimal
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from app.domain.approval import (
    Approval,
    ApprovalInvalidated,
    ApprovalKind,
    approve_plan,
    auto_approve,
    canonical_hash,
    check_before_submit,
    plan_approval_input,
)
from app.domain.video import Video, VideoStatus

pytestmark = pytest.mark.S03

scenarios("api/s03_approval.feature")


def sample_plan(plan_id: str) -> dict[str, Any]:
    return {
        "id": plan_id,
        "title": "古堡拿鐵",
        "shots": [
            {"shot_no": 1, "role": "hook", "duration_s": 4, "scene_photo_id": "wall"},
            {"shot_no": 2, "role": "feature", "duration_s": 5, "scene_photo_id": "stele"},
            {"shot_no": 3, "role": "cta", "duration_s": 3, "scene_photo_id": "tower"},
        ],
    }


def sample_placements() -> list[dict[str, Any]]:
    return [
        {"shot_no": n, "x": 0.5, "y": 0.85, "scale": 0.55, "flip": False} for n in (1, 2, 3)
    ]


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {"error": None}


# S03-01


@given(parsers.parse('一支狀態為 "{status}" 的影片，已選定企劃 "{plan_id}"'))
def video_with_selected_plan(ctx: dict[str, Any], status: str, plan_id: str) -> None:
    ctx["video"] = Video(status=VideoStatus(status))
    ctx["plan"] = sample_plan(plan_id)
    ctx["placements"] = sample_placements()


@when(parsers.parse("使用者以成本上限 {cap:d} 點核准企劃"))
def user_approves_plan(ctx: dict[str, Any], cap: int) -> None:
    ctx["approval"] = approve_plan(ctx["video"], ctx["plan"], ctx["placements"], Decimal(cap), "bonki")


@then(parsers.parse('產生一筆類型為 "{kind}" 的核准紀錄'))
def approval_of_kind(ctx: dict[str, Any], kind: str) -> None:
    approval: Approval = ctx["approval"]
    assert approval.kind == ApprovalKind(kind)
    assert approval.auto_approved is False
    assert approval.approved_by == "bonki"
    assert ctx["video"].status == VideoStatus.GENERATING


@then("核准紀錄包含企劃與擺放內容的輸入雜湊")
def approval_hash_covers_plan_and_placements(ctx: dict[str, Any]) -> None:
    expected = canonical_hash(plan_approval_input(ctx["plan"], ctx["placements"]))
    assert ctx["approval"].input_hash == expected


@then(parsers.parse("核准紀錄的成本上限為 {cap:d} 點"))
def approval_cost_cap(ctx: dict[str, Any], cap: int) -> None:
    assert ctx["approval"].cost_cap == Decimal(cap)


# S03-02


@given("兩份內容相同但欄位順序不同的企劃資料")
def two_plans_different_key_order(ctx: dict[str, Any]) -> None:
    plan = sample_plan("P1")
    reordered = {k: plan[k] for k in reversed(list(plan))}
    reordered["shots"] = [{k: s[k] for k in reversed(list(s))} for s in plan["shots"]]
    ctx["pair"] = (plan, reordered)


@when("分別計算輸入雜湊")
def hash_both(ctx: dict[str, Any]) -> None:
    ctx["hashes"] = [canonical_hash(p) for p in ctx["pair"]]


@then("兩個雜湊相同")
def hashes_equal(ctx: dict[str, Any]) -> None:
    first, second = ctx["hashes"]
    assert first == second


# S03-03、S03-04


@given(parsers.parse('企劃 "{plan_id}" 已被核准'))
def plan_already_approved(ctx: dict[str, Any], plan_id: str) -> None:
    ctx["video"] = Video(status=VideoStatus.PLAN_READY)
    ctx["plan"] = sample_plan(plan_id)
    ctx["placements"] = sample_placements()
    ctx["approval"] = approve_plan(
        ctx["video"], copy.deepcopy(ctx["plan"]), copy.deepcopy(ctx["placements"]), Decimal(140), "bonki"
    )


@given(parsers.parse("第 {shot_no:d} 鏡的角色擺放被修改"))
def placement_modified(ctx: dict[str, Any], shot_no: int) -> None:
    target = next(p for p in ctx["placements"] if p["shot_no"] == shot_no)
    target["x"] = 0.2


@when("系統在送出生成工作前重新計算輸入雜湊")
def recheck_before_submit(ctx: dict[str, Any]) -> None:
    ctx["current_input"] = plan_approval_input(ctx["plan"], ctx["placements"])
    try:
        check_before_submit(ctx["video"], ctx["approval"], ctx["current_input"])
    except ApprovalInvalidated as e:
        ctx["error"] = e


@then("雜湊與核准紀錄一致")
def hash_matches(ctx: dict[str, Any]) -> None:
    assert canonical_hash(ctx["current_input"]) == ctx["approval"].input_hash


@then("允許送出生成工作")
def submit_allowed(ctx: dict[str, Any]) -> None:
    assert ctx["error"] is None
    assert ctx["video"].status == VideoStatus.GENERATING


@then("拒絕送出生成工作")
def submit_rejected(ctx: dict[str, Any]) -> None:
    assert isinstance(ctx["error"], ApprovalInvalidated)


@then(parsers.parse('影片退回 "{status}" 等待重新確認'))
def video_returned(ctx: dict[str, Any], status: str) -> None:
    assert ctx["video"].status == VideoStatus(status)


# S03-05


@given("一支快速模式的影片")
def quick_mode_video(ctx: dict[str, Any]) -> None:
    ctx["video"] = Video(status=VideoStatus.GENERATING)
    ctx["script"] = {"shots": [{"shot_no": 1, "line": "1661 年，我來過這！"}]}


@when("系統自動採用建議的腳本")
def system_adopts_script(ctx: dict[str, Any]) -> None:
    ctx["approval"] = auto_approve(ApprovalKind.SCRIPT, ctx["script"])


@then("產生一筆 auto_approved 為 true 的核准紀錄")
def auto_approved_record(ctx: dict[str, Any]) -> None:
    approval: Approval = ctx["approval"]
    assert approval.auto_approved is True
    assert approval.kind == ApprovalKind.SCRIPT
    assert approval.approved_by is None
    assert approval.input_hash == canonical_hash(ctx["script"])
