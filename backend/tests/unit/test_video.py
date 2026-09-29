from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from app.domain.video import (
    TERMINAL,
    TRANSITIONS,
    InvalidTransition,
    Video,
    VideoEvent,
    VideoStatus,
)

pytestmark = pytest.mark.S02

S = VideoStatus
E = VideoEvent

# spec 0002 R-001 的轉換表
SPEC_TABLE = {
    (S.DRAFT, E.SUBMIT_TOPIC): S.PLANNING,
    (S.PLANNING, E.PLANS_READY): S.PLAN_READY,
    (S.PLANNING, E.PLANNING_FAILED): S.FAILED,
    (S.PLAN_READY, E.REGENERATE_PLANS): S.PLANNING,
    (S.PLAN_READY, E.APPROVE_PLAN): S.GENERATING,
    (S.GENERATING, E.ALL_SHOTS_DONE): S.RENDERING,
    (S.GENERATING, E.SHOT_FAILED_FINAL): S.NEEDS_ATTENTION,
    (S.GENERATING, E.APPROVAL_INVALIDATED): S.PLAN_READY,
    (S.NEEDS_ATTENTION, E.CONFIRM_REGENERATE): S.GENERATING,
    (S.NEEDS_ATTENTION, E.CONFIRM_RERENDER): S.RENDERING,
    (S.RENDERING, E.RENDER_DONE): S.REVIEW,
    (S.RENDERING, E.RENDER_RETRY): S.RENDERING,
    (S.RENDERING, E.RENDER_FAILED_FINAL): S.NEEDS_ATTENTION,
    (S.REVIEW, E.REGENERATE_SHOT): S.GENERATING,
    (S.REVIEW, E.APPROVE_FINAL): S.APPROVED,
}


def fixed_clock() -> Callable[[], datetime]:
    """每次呼叫前進 1 秒的固定時鐘。"""
    start = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    ticks = count()
    return lambda: start + timedelta(seconds=next(ticks))


def test_r001_transition_table_matches_spec() -> None:
    assert dict(TRANSITIONS) == SPEC_TABLE


@pytest.mark.parametrize(
    ("from_status", "event", "to_status"),
    [
        (S.GENERATING, E.APPROVAL_INVALIDATED, S.PLAN_READY),
        (S.NEEDS_ATTENTION, E.CONFIRM_RERENDER, S.RENDERING),
        (S.RENDERING, E.RENDER_RETRY, S.RENDERING),
        (S.RENDERING, E.RENDER_FAILED_FINAL, S.NEEDS_ATTENTION),
    ],
)
def test_r001_extra_transitions(from_status: S, event: E, to_status: S) -> None:
    video = Video(status=from_status)

    assert video.apply(event) == to_status
    assert video.status == to_status


def test_r002_all_undefined_pairs_rejected() -> None:
    undefined = [(s, e) for s in S for e in E if (s, e) not in SPEC_TABLE]
    assert len(undefined) == len(S) * len(E) - len(SPEC_TABLE)

    for status, event in undefined:
        video = Video(status=status)
        with pytest.raises(InvalidTransition):
            video.apply(event)
        assert video.status == status
        assert video.history == []


def test_r003_terminal_states_have_no_exit() -> None:
    assert frozenset({S.APPROVED, S.FAILED}) == TERMINAL
    for status in TERMINAL:
        for event in E:
            with pytest.raises(InvalidTransition):
                Video(status=status).apply(event)


def test_r003_every_non_terminal_state_has_exit() -> None:
    sources = {s for s, _ in TRANSITIONS}
    for status in S:
        if status not in TERMINAL:
            assert status in sources, f"{status} 沒有出口"


def test_r004_history_records_event_and_time() -> None:
    video = Video(clock=fixed_clock())

    video.apply(E.SUBMIT_TOPIC)
    video.apply(E.PLANS_READY)

    first, second = video.history
    assert (first.event, first.from_status, first.to_status) == (E.SUBMIT_TOPIC, S.DRAFT, S.PLANNING)
    assert (second.event, second.from_status, second.to_status) == (E.PLANS_READY, S.PLANNING, S.PLAN_READY)
    assert first.at.tzinfo is not None
    assert first.at < second.at
    assert video.status_trail == [S.DRAFT, S.PLANNING, S.PLAN_READY]


def test_r004_rejected_event_leaves_no_history() -> None:
    video = Video(clock=fixed_clock())
    video.apply(E.SUBMIT_TOPIC)

    with pytest.raises(InvalidTransition):
        video.apply(E.APPROVE_FINAL)

    assert len(video.history) == 1
    assert video.status == S.PLANNING
