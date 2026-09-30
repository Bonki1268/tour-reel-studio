import asyncio
import time
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, scenarios, then, when

from app.domain.approval import ApprovalKind
from app.providers.fake import FakeProvider
from tests.orchestration_support import ANCHOR_CARD, OrchEnv, is_subsequence

pytestmark = pytest.mark.S07


# 自動產生的名稱為 test_s0702_3_鏡…，正規化後編號緊接數字 3，閘門無法比對；改以明確名稱綁定
@scenario("api/s07_orchestration.feature", "S07-02 3 鏡平行生成")
def test_s0702_parallel_shots() -> None:
    pass


scenarios("api/s07_orchestration.feature")


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {}


def quoted(text: str) -> list[str]:
    return [s.strip().strip('"') for s in text.split(",")]


# Background


@given("一個含品牌檔案、1 個已鎖定角色與 3 張實景照的專案")
def project_with_assets(ctx: dict[str, Any]) -> None:
    ctx["env"] = OrchEnv()


@given("使用 FakeCreativeEngine、FakeProvider、FakeRenderer 與記憶體儲存")
def fake_dependencies(ctx: dict[str, Any]) -> None:
    env: OrchEnv = ctx["env"]
    asyncio.run(env.setup_project())


# S07-01


@when(parsers.parse('使用者送出主題 "{topic}"'))
def submit_topic(ctx: dict[str, Any], topic: str) -> None:
    env: OrchEnv = ctx["env"]
    ctx["video_id"] = asyncio.run(env.to_plan_ready(topic))
    ctx["topic"] = topic


@then(parsers.parse('影片狀態變為 "{status}" 並有 2 到 3 個企劃'))
def plan_ready_with_plans(ctx: dict[str, Any], status: str) -> None:
    env: OrchEnv = ctx["env"]
    assert asyncio.run(env.video_status(ctx["video_id"])) == status
    plans = asyncio.run(env.repos.plans.list(ctx["video_id"]))
    assert 2 <= len(plans) <= 3
    (plan_ctx,) = env.engine.contexts
    assert plan_ctx.topic == ctx["topic"]
    assert plan_ctx.anchor_card == ANCHOR_CARD
    assert [p.id for p in plan_ctx.scene_photos] == [p.id for p in env.photos]
    assert plan_ctx.brand.project_id == env.project_id


@when("使用者選擇第 1 個企劃並以預估上限核准")
def approve_first_plan(ctx: dict[str, Any]) -> None:
    env: OrchEnv = ctx["env"]
    asyncio.run(env.approve_first_plan(ctx["video_id"]))
    asyncio.run(env.orch.generate(ctx["video_id"]))


@then("3 個鏡頭各自產生關鍵幀與影片")
def three_shots_done(ctx: dict[str, Any]) -> None:
    env: OrchEnv = ctx["env"]
    shots = asyncio.run(env.shots(ctx["video_id"]))
    assert [s.shot_no for s, _ in shots] == [1, 2, 3]
    for n in (1, 2, 3):
        assert asyncio.run(env.shot_done(ctx["video_id"], n))


@then(parsers.parse("影片狀態依序經過 {statuses}"))
def status_passes_through(ctx: dict[str, Any], statuses: str) -> None:
    env: OrchEnv = ctx["env"]
    trail = asyncio.run(env.status_trail(ctx["video_id"]))
    expected = quoted(statuses)
    assert is_subsequence(expected, trail), trail
    assert trail[-1] == expected[-1]


@then("產生一份時間軸 JSON 與一個成品檔")
def timeline_and_output(ctx: dict[str, Any]) -> None:
    env: OrchEnv = ctx["env"]
    video = asyncio.run(env.repos.videos.get(ctx["video_id"]))
    assert video is not None and isinstance(video.timeline, dict) and video.timeline
    (render,) = asyncio.run(env.repos.renders.list(ctx["video_id"]))
    assert render.mp4_key == f"videos/{ctx['video_id']}/renders/{render.id}.mp4"
    assert asyncio.run(env.storage.exists(render.mp4_key))


# S07-02


@given(parsers.parse("FakeProvider 每個工作耗時 {seconds:d} 秒"))
def provider_takes(ctx: dict[str, Any], seconds: int) -> None:
    env: OrchEnv = ctx["env"]
    env.real_time = True
    env.provider = FakeProvider(duration_s=seconds)
    ctx["duration"] = seconds


@given(parsers.parse("FakeProvider 對第 {shot_no:d} 鏡永遠失敗"))
def provider_fails_for_shot(ctx: dict[str, Any], shot_no: int) -> None:
    ctx["env"].provider = FakeProvider(outcomes_by_shot={shot_no: ("fail",)})


@when("核准企劃後開始生成")
def approve_and_generate(ctx: dict[str, Any]) -> None:
    env: OrchEnv = ctx["env"]
    video_id = asyncio.run(env.to_plan_ready())
    asyncio.run(env.approve_first_plan(video_id))
    started = time.monotonic()
    asyncio.run(env.orch.generate(video_id))
    ctx.update(video_id=video_id, elapsed=time.monotonic() - started)


@then(parsers.parse("所有鏡頭在 {seconds:d} 秒內完成生成"))
def all_shots_within(ctx: dict[str, Any], seconds: int) -> None:
    env: OrchEnv = ctx["env"]
    for n in (1, 2, 3):
        assert asyncio.run(env.shot_done(ctx["video_id"], n))
    # 每鏡關鍵幀＋影片各耗時 1 秒：平行約 2 秒，循序需 6 秒
    assert 2 * ctx["duration"] <= ctx["elapsed"] < seconds


# S07-03、S07-06


@when("完成一次完整快速流程")
def complete_flow(ctx: dict[str, Any]) -> None:
    ctx["video_id"] = asyncio.run(ctx["env"].full_flow())


@then(parsers.parse("進度事件依序包含 {types}"))
def events_in_order(ctx: dict[str, Any], types: str) -> None:
    actual = ctx["env"].event_types()
    assert is_subsequence(quoted(types), actual), actual


@then("每個事件都帶有 video_id")
def events_have_video_id(ctx: dict[str, Any]) -> None:
    events = ctx["env"].bus.events
    assert events
    for e in events:
        assert e.video_id == ctx["video_id"]
        assert e.at is not None
        if e.type.startswith("shot_"):
            assert e.shot_no in (1, 2, 3)


@then(parsers.parse('使用者核准紀錄只有 "{first}" 與 "{second}" 兩筆'))
def user_approvals_only(ctx: dict[str, Any], first: str, second: str) -> None:
    approvals = asyncio.run(ctx["env"].repos.approvals.list(ctx["video_id"]))
    ctx["approvals"] = approvals
    assert sorted(a.kind for a in approvals if not a.auto_approved) == sorted([first, second])


@then("其餘核准紀錄的 auto_approved 皆為 true")
def others_auto_approved(ctx: dict[str, Any]) -> None:
    others = [a for a in ctx["approvals"] if a.kind not in (ApprovalKind.PLAN, ApprovalKind.FINAL)]
    assert others and all(a.auto_approved for a in others)
    kinds = [a.kind for a in others]
    assert kinds.count(ApprovalKind.SCRIPT) == 1
    assert kinds.count(ApprovalKind.ASSETS) == 1
    assert kinds.count(ApprovalKind.KEYFRAMES) == 3


# S07-04


@then(parsers.parse("第 {a:d} 鏡與第 {b:d} 鏡完成"))
def shots_completed(ctx: dict[str, Any], a: int, b: int) -> None:
    env: OrchEnv = ctx["env"]
    assert asyncio.run(env.shot_done(ctx["video_id"], a))
    assert asyncio.run(env.shot_done(ctx["video_id"], b))


@then(parsers.parse('影片狀態變為 "{status}"'))
def video_status_becomes(ctx: dict[str, Any], status: str) -> None:
    env: OrchEnv = ctx["env"]
    assert asyncio.run(env.video_status(ctx["video_id"])) == status
    failed = [e for e in env.bus.events if e.type == "shot_failed"]
    assert [e.shot_no for e in failed] == [2]
    assert "needs_attention" in env.event_types()
    assert "render_started" not in env.event_types()


# S07-05


@given(parsers.parse('一支狀態為 "{status}" 的影片'))
def video_in_review(ctx: dict[str, Any], status: str) -> None:
    env: OrchEnv = ctx["env"]
    ctx["video_id"] = asyncio.run(env.to_review())
    assert asyncio.run(env.video_status(ctx["video_id"])) == status
    ctx["before"] = {s.shot_no: (t.id if t else None) for s, t in asyncio.run(env.shots(ctx["video_id"]))}
    ctx["submissions"] = len(env.provider.submissions)


@when(parsers.parse("使用者重生第 {shot_no:d} 鏡"))
def regenerate(ctx: dict[str, Any], shot_no: int) -> None:
    asyncio.run(ctx["env"].orch.regenerate_shot(ctx["video_id"], shot_no))
    ctx["regenerated"] = shot_no


@then(parsers.parse("只有第 {shot_no:d} 鏡產生新版本"))
def only_shot_regenerated(ctx: dict[str, Any], shot_no: int) -> None:
    env: OrchEnv = ctx["env"]
    for shot, take in asyncio.run(env.shots(ctx["video_id"])):
        takes = asyncio.run(env.repos.shots.takes(shot.id))
        if shot.shot_no == shot_no:
            assert [t.attempt for t in takes] == [1, 2]
            assert take is not None and take.attempt == 2
        else:
            assert len(takes) == 1
            assert take is not None and take.id == ctx["before"][shot.shot_no]
    new_requests = env.provider.submissions[ctx["submissions"]:]
    assert new_requests and {r.input["shot_no"] for r in new_requests} == {shot_no}
    assert asyncio.run(env.shot_done(ctx["video_id"], shot_no))


@then("成品重新合成")
def rerendered(ctx: dict[str, Any]) -> None:
    assert len(asyncio.run(ctx["env"].repos.renders.list(ctx["video_id"]))) == 2


@then(parsers.parse('影片回到 "{status}"'))
def back_to(ctx: dict[str, Any], status: str) -> None:
    trail = asyncio.run(ctx["env"].status_trail(ctx["video_id"]))
    assert trail[-4:] == ["review", "generating", "rendering", status]
