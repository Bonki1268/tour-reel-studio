import asyncio
from datetime import timedelta
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from app.domain.approval import ApprovalInvalidated
from app.domain.generation import JobStatus
from app.providers.fake import FakeProvider
from tests.generation_support import JOB_KINDS, GenEnv, keyframe_key

pytestmark = pytest.mark.S06

scenarios("api/s06_generation_job.feature")


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {}


def env_with(ctx: dict[str, Any], provider: FakeProvider) -> GenEnv:
    ctx["env"] = GenEnv(provider=provider)
    return ctx["env"]


# Given


@given("FakeProvider 設定為成功")
def provider_succeeds(ctx: dict[str, Any]) -> None:
    env_with(ctx, FakeProvider(("succeed",), running_polls=1, content=b"\x89PNG-keyframe"))


@given("FakeProvider 設定為第 1 次失敗、第 2 次成功")
def provider_fails_then_succeeds(ctx: dict[str, Any]) -> None:
    env_with(ctx, FakeProvider(("fail", "succeed")))


@given("FakeProvider 設定為永遠失敗")
def provider_always_fails(ctx: dict[str, Any]) -> None:
    env_with(ctx, FakeProvider(("fail",)))


@given("FakeProvider 設定為永不完成")
def provider_never_completes(ctx: dict[str, Any]) -> None:
    env_with(ctx, FakeProvider(("never",)))


@given(parsers.parse("工作逾時設定為 {seconds:d} 秒"))
def job_timeout(ctx: dict[str, Any], seconds: int) -> None:
    ctx["env"].timeout_s = seconds


@given("一個已成功並已記帳的工作")
def stored_and_charged_job(ctx: dict[str, Any]) -> None:
    env = env_with(ctx, FakeProvider(("succeed",)))
    ctx["first"] = asyncio.run(env.run(JOB_KINDS["關鍵幀"]))
    assert ctx["first"].status == JobStatus.STORED
    assert env.ctx is not None
    ctx["submissions"] = len(env.provider.submissions)
    ctx["fetches"] = len(env.provider.fetches)
    ctx["costs"] = len(asyncio.run(env.repos.costs.list(env.video.id)))  # type: ignore[union-attr]
    assert ctx["costs"] == 1


@given("企劃已核准但第 1 鏡的輸入在核准後被修改")
def input_modified_after_approval(ctx: dict[str, Any]) -> None:
    env = env_with(ctx, FakeProvider(("succeed",)))
    env.modify_after_approval = True


# When


@when(parsers.parse("執行一個{kind}生成工作"))
def run_job(ctx: dict[str, Any], kind: str) -> None:
    env: GenEnv = ctx["env"]
    ctx["result"] = asyncio.run(env.run(JOB_KINDS[kind]))


@when("以相同冪等鍵再次執行")
def run_again(ctx: dict[str, Any]) -> None:
    env: GenEnv = ctx["env"]
    ctx["result"] = asyncio.run(env.run(JOB_KINDS["關鍵幀"]))


@when(parsers.parse("執行第 1 鏡的{kind}生成工作"))
def run_shot1_job(ctx: dict[str, Any], kind: str) -> None:
    env: GenEnv = ctx["env"]
    with pytest.raises(ApprovalInvalidated):
        asyncio.run(env.run(JOB_KINDS[kind]))


# Then


@then(parsers.parse("工作狀態依序為 {statuses}"))
def statuses_in_order(ctx: dict[str, Any], statuses: str) -> None:
    expected = [s.strip().strip('"') for s in statuses.split(",")]
    assert ctx["env"].statuses(1) == expected


@then("結果已存入物件儲存")
def result_stored(ctx: dict[str, Any]) -> None:
    env: GenEnv = ctx["env"]
    key = keyframe_key(env)
    assert asyncio.run(env.storage.get(key)) == b"\x89PNG-keyframe"
    takes = asyncio.run(env.repos.shots.takes(env.shot.id))  # type: ignore[union-attr]
    assert takes[-1].keyframe_key == key


@then("工作記錄外部 request ID")
def external_id_recorded(ctx: dict[str, Any]) -> None:
    env: GenEnv = ctx["env"]
    job = asyncio.run(env.repos.jobs.get(ctx["result"].id))
    assert job is not None and job.external_id
    assert job.external_id == env.provider.external_ids[0]


@then(parsers.parse('工作最終狀態為 "{status}"'))
def final_status(ctx: dict[str, Any], status: str) -> None:
    assert ctx["result"].status == status
    assert ctx["result"].attempt == 2


@then(parsers.parse("工作共送出 {n:d} 次"))
def submitted_n_times(ctx: dict[str, Any], n: int) -> None:
    subs = ctx["env"].provider.submissions
    assert len(subs) == n
    assert len({s.provider_idempotency_key for s in subs}) == n


@then(parsers.parse('所屬影片狀態變為 "{status}"'))
def video_status_is(ctx: dict[str, Any], status: str) -> None:
    assert asyncio.run(ctx["env"].video_status()) == status


@then("工作被判定為逾時失敗並觸發重試")
def timed_out_and_retried(ctx: dict[str, Any]) -> None:
    env: GenEnv = ctx["env"]
    first, second = asyncio.run(env.attempts())
    assert first.status == JobStatus.FAILED
    assert first.error is not None and first.error.startswith("timeout")
    assert first.submitted_at is not None and second.submitted_at is not None
    # 第 1 次在送出後 1 秒（加上最多一個輪詢間隔）被判定逾時，接著送出第 2 次
    waited = second.submitted_at - first.submitted_at
    assert timedelta(seconds=1) <= waited <= timedelta(seconds=1 + env.poll_interval_s)
    assert len(env.provider.submissions) == 2


@then("不會再次呼叫供應商")
def provider_not_called_again(ctx: dict[str, Any]) -> None:
    env: GenEnv = ctx["env"]
    assert len(env.provider.submissions) == ctx["submissions"]
    assert len(env.provider.fetches) == ctx["fetches"]
    assert ctx["result"] == ctx["first"]


@then("成本帳沒有新增紀錄")
def no_new_cost_entry(ctx: dict[str, Any]) -> None:
    env: GenEnv = ctx["env"]
    assert len(asyncio.run(env.repos.costs.list(env.video.id))) == ctx["costs"]  # type: ignore[union-attr]


@then("不會呼叫供應商")
def provider_never_called(ctx: dict[str, Any]) -> None:
    env: GenEnv = ctx["env"]
    assert env.provider.submissions == []
    assert env.provider.fetches == []


@then(parsers.parse('影片退回 "{status}"'))
def video_back_to(ctx: dict[str, Any], status: str) -> None:
    assert asyncio.run(ctx["env"].video_status()) == status
