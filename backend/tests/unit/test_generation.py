"""生成工作：領域規則與執行流程（spec 0006）。"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain.cost import Budget, BudgetExceeded, CostEntry, JobKind
from app.domain.generation import InvalidJobTransition, JobStatus, advance, should_retry, timed_out
from app.domain.ids import new_id
from app.jobs.generation import build_attempt, run_generation_job
from app.providers.base import ProviderRequest
from app.providers.fake import FakeProvider
from tests.generation_support import KEYFRAME_PRICE, VIDEO_PRICE, GenEnv
from tests.persistence_data import make_job

pytestmark = pytest.mark.S06

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


# 領域規則


def test_r002_max_two_attempts() -> None:
    assert should_retry(1, retryable=True) is True
    assert should_retry(2, retryable=True) is False


def test_r003_non_retryable_not_retried() -> None:
    assert should_retry(1, retryable=False) is False


def test_r004_timeout_counts_from_submitted() -> None:
    assert timed_out(T0, T0 + timedelta(seconds=0.999), 1) is False
    assert timed_out(T0, T0 + timedelta(seconds=1), 1) is True


def test_r001_job_transitions_follow_table() -> None:
    job = make_job(new_id(), "v1:1:keyframe:abc:1")
    for to in (JobStatus.SUBMITTED, JobStatus.RUNNING, JobStatus.SUCCEEDED, JobStatus.STORED):
        advance(job, to)
    assert job.status == JobStatus.STORED


def test_r001_invalid_job_transition_rejected() -> None:
    job = make_job(new_id(), "v1:1:keyframe:abc:1")
    with pytest.raises(InvalidJobTransition):
        advance(job, JobStatus.STORED)
    assert job.status == JobStatus.QUEUED
    advance(job, JobStatus.FAILED, error="boom")
    assert job.error == "boom"
    with pytest.raises(InvalidJobTransition):
        advance(job, JobStatus.SUBMITTED)


def test_r007_budget_release_frees_reservation() -> None:
    budget = Budget(cap=Decimal("5"))
    budget.check("job-1", Decimal("4"))
    budget.release("job-1")
    budget.check("job-2", Decimal("5"))
    budget.release("unknown-job")  # 沒有預留時不報錯
    assert budget.reserved == {"job-2": Decimal("5")}


# 執行流程


async def test_r003_non_retryable_goes_failed_final() -> None:
    env = GenEnv(provider=FakeProvider(("fail_non_retryable",)))

    job = await env.run(JobKind.VIDEO)

    assert job.status == JobStatus.FAILED_FINAL
    assert job.attempt == 1
    assert len(env.provider.submissions) == 1
    assert await env.video_status() == "needs_attention"


async def test_r003_retry_failure_charges_nothing() -> None:
    env = GenEnv(provider=FakeProvider(("fail",)))

    await env.run(JobKind.VIDEO)

    assert env.video is not None
    assert await env.repos.costs.list(env.video.id) == []


async def test_r004_queue_time_not_counted() -> None:
    clock_env = GenEnv(timeout_s=1)
    # 送出本身耗時 5 秒（排隊與送出前），送出後 0.4 秒完成：不應逾時
    clock_env.provider = FakeProvider(
        ("succeed",), running_polls=2, on_submit=lambda: clock_env.clock.advance(5)
    )

    job = await clock_env.run(JobKind.KEYFRAME)

    assert job.status == JobStatus.STORED
    assert len(clock_env.provider.submissions) == 1


async def test_r005_resume_existing_external_id() -> None:
    env = GenEnv(provider=FakeProvider(("succeed",), running_polls=1))
    ctx = await env.setup()
    spec = env.spec(JobKind.KEYFRAME)
    # 模擬 Worker 在送出後重啟：工作已有 external_id，但尚未完成
    job = build_attempt(ctx, spec, 1)
    pjob = await env.provider.compose(
        ProviderRequest(job.model, spec.input_snapshot, job.provider_idempotency_key or "")
    )
    job.external_id = pjob.external_id
    job.submitted_at = env.clock()
    job.status = JobStatus.SUBMITTED
    await env.repos.jobs.create_or_get(job)

    result = await run_generation_job(ctx, spec)

    assert len(env.provider.submissions) == 1  # 只有重啟前那一次
    assert result.id == job.id
    assert result.status == JobStatus.STORED
    assert env.provider.fetches and set(env.provider.fetches) == {pjob.external_id}


async def test_r005_different_input_hash_is_new_job() -> None:
    env = GenEnv()
    first = await env.run(JobKind.KEYFRAME, snapshot={"prompt": "梅子園晨光"})

    second = await env.run(JobKind.KEYFRAME, snapshot={"prompt": "梅子園黃昏"})

    assert second.id != first.id
    assert second.idempotency_key != first.idempotency_key
    assert second.status == JobStatus.STORED
    assert len(env.provider.submissions) == 2


async def test_r005_regenerated_take_is_new_job() -> None:
    env = GenEnv()
    first = await env.run(JobKind.KEYFRAME)
    assert env.shot is not None
    new_take = await env.repos.shots.add_take(env.shot.id)

    second = await env.run(JobKind.KEYFRAME, take=new_take)

    assert second.id != first.id
    assert len(env.provider.submissions) == 2


async def test_r007_budget_exceeded_no_submit() -> None:
    env = GenEnv(cap=Decimal("1"))

    with pytest.raises(BudgetExceeded) as exc:
        await env.run(JobKind.KEYFRAME)

    assert exc.value.requires_reconfirmation is True
    assert env.provider.submissions == []
    (job,) = await env.attempts()
    assert job.status == JobStatus.QUEUED
    assert job.error == "budget_exceeded"


async def test_r007_retry_blocked_by_budget() -> None:
    env = GenEnv(cap=Decimal("8"))

    def other_shot_reserves() -> None:
        assert env.ctx is not None
        env.ctx.budget.reserved["other-shot"] = Decimal("4.5")

    env.provider = FakeProvider(("fail", "succeed"), on_submit=other_shot_reserves)

    with pytest.raises(BudgetExceeded):
        await env.run(JobKind.VIDEO)

    assert len(env.provider.submissions) == 1
    first, second = await env.attempts()
    assert first.status == JobStatus.FAILED
    assert (second.attempt, second.status, second.error) == (2, JobStatus.QUEUED, "budget_exceeded")


async def test_r007_records_provider_cost_once() -> None:
    env = GenEnv(provider=FakeProvider(("succeed",), actual_cost=Decimal("1.8")))
    job = await env.run(JobKind.KEYFRAME)

    await env.run(JobKind.KEYFRAME)

    assert env.video is not None
    assert await env.repos.costs.list(env.video.id) == [CostEntry(job.id, Decimal("1.8"), "provider")]
    assert job.actual_cost == Decimal("1.8")


async def test_r007_records_table_cost_when_unreported() -> None:
    env = GenEnv(provider=FakeProvider(("succeed",), actual_cost=None))

    job = await env.run(JobKind.VIDEO)

    assert env.video is not None
    assert await env.repos.costs.list(env.video.id) == [CostEntry(job.id, VIDEO_PRICE, "table")]


async def test_r007_failed_attempt_releases_reservation() -> None:
    env = GenEnv(provider=FakeProvider(("fail",)))

    await env.run(JobKind.KEYFRAME)

    assert env.ctx is not None
    assert env.ctx.budget.reserved == {}
    assert env.ctx.budget.spent == Decimal(0)
    assert KEYFRAME_PRICE > 0
