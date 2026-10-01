"""編排串接合成：縮圖與合成失敗重試（spec 0013 R-006、R-007）。"""

from collections.abc import Mapping
from typing import Any

import pytest

from app.domain.ports import Storage
from app.render.fake import FakeRenderer
from app.render.ffmpeg import RenderError
from app.render.timeline import Timeline
from app.storage import keys
from tests.orchestration_support import OrchEnv

pytestmark = pytest.mark.S13


class FlakyRenderer(FakeRenderer):
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def render(
        self, timeline: Mapping[str, Any], storage: Storage, output_key: str, thumb_key: str | None = None
    ) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise RenderError("ffmpeg exited with 1")
        await super().render(timeline, storage, output_key, thumb_key)


async def test_r006_render_record_has_thumb_key() -> None:
    env = OrchEnv()
    video_id = await env.to_review()
    renders = await env.repos.renders.list(video_id)
    assert len(renders) == 1
    assert renders[0].thumb_key == keys.render_thumb(video_id, renders[0].id)
    assert await env.storage.exists(renders[0].thumb_key)
    assert keys.render_thumb("v", "r") == "videos/v/renders/r.jpg"


async def test_r006_timeline_uses_brand_color_and_validates() -> None:
    env = OrchEnv()
    video_id = await env.to_review()
    video = await env.repos.videos.get(video_id)
    assert video is not None
    timeline = Timeline.model_validate(video.timeline)
    assert timeline.style.primary_color == "#6B8E23"  # 品牌檔案的第一個顏色
    assert len(timeline.video_clips) == 3


async def test_r007_render_retry_then_success() -> None:
    renderer = FlakyRenderer(failures=1)
    env = OrchEnv(renderer=renderer)
    video_id = await env.to_review()
    assert renderer.calls == 2
    assert await env.video_status(video_id) == "review"
    assert len(await env.repos.renders.list(video_id)) == 1


async def test_r007_render_fails_twice_needs_attention() -> None:
    renderer = FlakyRenderer(failures=2)
    env = OrchEnv(renderer=renderer)
    video_id = await env.to_review()
    assert renderer.calls == 2
    assert await env.video_status(video_id) == "needs_attention"
    assert "render_failed" in env.event_types()
    assert "review_ready" not in env.event_types()
    assert await env.repos.renders.list(video_id) == []
    failed = next(e for e in env.bus.events if e.type == "render_failed")
    assert "ffmpeg exited with 1" in failed.data["error"]
