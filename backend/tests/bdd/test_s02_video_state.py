import re
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from app.domain.video import InvalidTransition, Video, VideoEvent, VideoStatus

pytestmark = pytest.mark.S02

scenarios("api/s02_video_state.feature")


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {"error": None}


@given(parsers.parse('一支狀態為 "{status}" 的影片'), target_fixture="video")
def video_in_status(status: str) -> Video:
    return Video(status=VideoStatus(status))


@when(parsers.parse('發生事件 "{event}"'))
def apply_event(video: Video, ctx: dict[str, Any], event: str) -> None:
    try:
        video.apply(VideoEvent(event))
    except InvalidTransition as e:
        ctx["error"] = e


@when(parsers.parse('依序發生事件 "{first}" 與 "{second}"'))
def apply_events(video: Video, first: str, second: str) -> None:
    video.apply(VideoEvent(first))
    video.apply(VideoEvent(second))


@then(parsers.parse('影片狀態變為 "{status}"'))
def status_becomes(video: Video, ctx: dict[str, Any], status: str) -> None:
    assert ctx["error"] is None
    assert video.status == VideoStatus(status)


@then("應拋出狀態轉換錯誤")
def transition_rejected(ctx: dict[str, Any]) -> None:
    assert isinstance(ctx["error"], InvalidTransition)


@then(parsers.parse('影片狀態仍為 "{status}"'))
def status_unchanged(video: Video, status: str) -> None:
    assert video.status == VideoStatus(status)
    assert video.history == []


@then(parsers.parse("影片的狀態歷程依序為 {trail}"))
def trail_is(video: Video, trail: str) -> None:
    expected = [VideoStatus(s) for s in re.findall(r'"([^"]+)"', trail)]
    assert video.status_trail == expected
    assert all(change.event and change.at for change in video.history)
