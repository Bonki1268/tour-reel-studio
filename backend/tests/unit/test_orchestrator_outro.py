"""編排串接片尾（spec 0014 R-007）。"""

import pytest

from app.domain.ports import Storage
from app.render.fake import FakeRenderer
from app.render.ffmpeg import RenderError
from app.render.outro import OutroInfo
from app.render.timeline import Timeline
from app.storage import keys
from tests.orchestration_support import OrchEnv

pytestmark = pytest.mark.S14


class RecordingRenderer(FakeRenderer):
    def __init__(self, outro_failures: int = 0) -> None:
        self.outros: list[tuple[OutroInfo, str]] = []
        self.outro_failures = outro_failures

    async def render_outro(self, info: OutroInfo, storage: Storage, key: str) -> None:
        self.outros.append((info, key))
        if len(self.outros) <= self.outro_failures:
            raise RenderError("outro failed")
        await super().render_outro(info, storage, key)


async def test_r007_outro_in_timeline() -> None:
    renderer = RecordingRenderer()
    env = OrchEnv(renderer=renderer)
    video_id = await env.to_review()
    assert len(renderer.outros) == 1
    info, key = renderer.outros[0]
    assert key == keys.outro(video_id) == f"videos/{video_id}/outro.mp4"
    assert info.name == "梅子農場" and info.primary_color == "#6B8E23"
    assert await env.storage.exists(key)
    video = await env.repos.videos.get(video_id)
    assert video is not None
    timeline = Timeline.model_validate(video.timeline)
    last = timeline.video_clips[-1]
    assert (last.asset, last.source, last.duration) == (key, "template", 3)
    shots_total = sum(s.duration_s for s, _ in await env.shots(video_id))
    assert timeline.duration == pytest.approx(shots_total + 3)


async def test_r007_outro_failure_retried() -> None:
    renderer = RecordingRenderer(outro_failures=1)
    env = OrchEnv(renderer=renderer)
    video_id = await env.to_review()
    assert len(renderer.outros) == 2
    assert await env.video_status(video_id) == "review"


async def test_r007_outro_fails_twice_needs_attention() -> None:
    renderer = RecordingRenderer(outro_failures=2)
    env = OrchEnv(renderer=renderer)
    video_id = await env.to_review()
    assert await env.video_status(video_id) == "needs_attention"
    assert "render_failed" in env.event_types()
