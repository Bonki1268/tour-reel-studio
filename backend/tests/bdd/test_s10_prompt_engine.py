import asyncio
from dataclasses import replace
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from app.creative.prompt_engine import PlanGenerationError, PromptEngine
from tests.claude_support import ANCHOR_CARD, RecordedClaude, engine_settings, fixture_text, plan_context

pytestmark = pytest.mark.S10

scenarios("api/s10_prompt_engine.feature")


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {}


def quoted(text: str) -> list[str]:
    return [s.strip().strip('"') for s in text.split(",")]


def engine(ctx: dict[str, Any]) -> PromptEngine:
    ctx["claude"] = RecordedClaude(ctx["replies"])
    return PromptEngine(ctx["claude"], engine_settings())


# Background


@given("使用預錄的 Claude 回應 fixture")
def recorded_fixture(ctx: dict[str, Any]) -> None:
    ctx["replies"] = [fixture_text("valid_plans.json")]


@given(parsers.parse('一個品牌語氣為 "{tone}"、含 {count:d} 張實景照的專案'))
def project(ctx: dict[str, Any], tone: str, count: int) -> None:
    ctx["plan_ctx"] = plan_context(tone=tone, photo_count=count)


# S10-01～S10-04


@given("Claude 第 1 次回傳無效 JSON，第 2 次回傳有效企劃")
def invalid_then_valid(ctx: dict[str, Any]) -> None:
    ctx["replies"] = [fixture_text("invalid_json.txt"), fixture_text("valid_plans.json")]


@given("Claude 連續回傳無效 JSON")
def always_invalid(ctx: dict[str, Any]) -> None:
    ctx["replies"] = [fixture_text("invalid_json.txt")]


@given(parsers.parse('Claude 第 1 次回傳引用 "{photo_id}" 的企劃，第 2 次回傳有效企劃'))
def missing_photo_then_valid(ctx: dict[str, Any], photo_id: str) -> None:
    first = fixture_text("missing_photo.json")
    assert f'"{photo_id}"' in first
    ctx["replies"] = [first, fixture_text("valid_plans.json")]


@when(parsers.parse('以主題 "{topic}" 產生企劃'))
def propose(ctx: dict[str, Any], topic: str) -> None:
    plan_ctx = ctx["plan_ctx"] = replace(ctx["plan_ctx"], topic=topic)
    try:
        ctx["plans"] = asyncio.run(engine(ctx).propose_plans(plan_ctx))
    except PlanGenerationError as e:
        ctx["error"] = e


@then(parsers.parse("回傳 {low:d} 到 {high:d} 個企劃"))
def plan_count(ctx: dict[str, Any], low: int, high: int) -> None:
    assert low <= len(ctx["plans"]) <= high


@then(parsers.parse("每個企劃有 {n:d} 鏡，功能依序為 {roles}"))
def shot_roles(ctx: dict[str, Any], n: int, roles: str) -> None:
    for plan in ctx["plans"]:
        assert len(plan.shots) == n
        assert [s.role for s in plan.shots] == quoted(roles)
        assert [s.shot_no for s in plan.shots] == [1, 2, 3]


@then(parsers.parse("3 鏡長度合計 {total:d} 秒"))
def duration_sum(ctx: dict[str, Any], total: int) -> None:
    for plan in ctx["plans"]:
        assert sum(s.duration_s for s in plan.shots) == pytest.approx(total)


@then("每鏡引用的實景照都存在於專案中")
def photos_exist(ctx: dict[str, Any]) -> None:
    ids = {p.id for p in ctx["plan_ctx"].scene_photos}
    assert all(s.scene_photo_id in ids for plan in ctx["plans"] for s in plan.shots)


@then("每鏡的擺放參數 x、y、scale 都介於 0 到 1")
def placement_range(ctx: dict[str, Any]) -> None:
    for plan in ctx["plans"]:
        for s in plan.shots:
            assert 0 <= s.placement["x"] <= 1
            assert 0 <= s.placement["y"] <= 1
            assert 0 < s.placement["scale"] <= 1


@then("成功回傳企劃")
def succeeded(ctx: dict[str, Any]) -> None:
    assert "error" not in ctx
    assert 2 <= len(ctx["plans"]) <= 3
    ids = {p.id for p in ctx["plan_ctx"].scene_photos}
    assert all(s.scene_photo_id in ids for plan in ctx["plans"] for s in plan.shots)


@then(parsers.parse("共呼叫 Claude {n:d} 次"))
def call_count(ctx: dict[str, Any], n: int) -> None:
    assert len(ctx["claude"].requests) == n


@then("應拋出企劃產生錯誤")
def raised(ctx: dict[str, Any]) -> None:
    assert isinstance(ctx.get("error"), PlanGenerationError)
    assert "plans" not in ctx
    assert len(ctx["claude"].requests) == 2


# S10-05


@when("組出送給 Claude 的提示詞")
def build_prompt(ctx: dict[str, Any]) -> None:
    system, user = engine(ctx).build_prompt(ctx["plan_ctx"])
    ctx["prompt"] = f"{system}\n{user}"


@then(parsers.parse('提示詞包含品牌語氣 "{tone}"'))
def prompt_has_tone(ctx: dict[str, Any], tone: str) -> None:
    assert tone in ctx["prompt"]


@then("提示詞包含角色身份錨點")
def prompt_has_anchor(ctx: dict[str, Any]) -> None:
    assert ANCHOR_CARD["anchor_zh"] in ctx["prompt"]


@then("提示詞包含每張實景照的描述")
def prompt_has_photos(ctx: dict[str, Any]) -> None:
    for photo in ctx["plan_ctx"].scene_photos:
        assert photo.id in ctx["prompt"]
        assert photo.description in ctx["prompt"]


@then("提示詞要求以繁體中文輸出")
def prompt_requires_zh_tw(ctx: dict[str, Any]) -> None:
    assert "繁體中文" in ctx["prompt"]


# S10-06


@given("一個已核准的企劃")
def approved_plan(ctx: dict[str, Any]) -> None:
    ctx["plan"] = asyncio.run(engine(ctx).propose_plans(ctx["plan_ctx"]))[0]


@when("產生 3 鏡的生成提示詞")
def shot_prompts(ctx: dict[str, Any]) -> None:
    ctx["shot_prompts"] = asyncio.run(engine(ctx).build_shot_prompts(ctx["plan"], ctx["plan_ctx"]))


@then("每鏡都有關鍵幀提示詞與影片提示詞")
def prompts_present(ctx: dict[str, Any]) -> None:
    prompts = ctx["shot_prompts"]
    assert [p.shot_no for p in prompts] == [1, 2, 3]
    assert all(p.keyframe_prompt.strip() and p.video_prompt.strip() for p in prompts)


@then("影片提示詞包含鏡頭運動描述")
def video_prompt_has_camera(ctx: dict[str, Any]) -> None:
    for shot, prompt in zip(ctx["plan"].shots, ctx["shot_prompts"], strict=True):
        assert shot.camera_en and shot.camera_en in prompt.video_prompt
        assert ANCHOR_CARD["anchor_en"] in prompt.video_prompt
        assert shot.action_en in prompt.video_prompt
        assert "no on-screen text" in prompt.video_prompt
