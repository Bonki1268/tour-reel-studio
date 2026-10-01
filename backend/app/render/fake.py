"""FakeRenderer：產生與 FFmpeg 合成器相同格式的時間軸 JSON，成品與縮圖為空檔（spec 0007、0013）。"""

from collections.abc import Mapping
from typing import Any

from app.domain.ports import Shot, ShotTake, Storage, VideoRecord
from app.render.outro import OutroInfo
from app.render.timeline import Style, timeline_from_shots


class FakeRenderer:
    def build_timeline(
        self,
        video: VideoRecord,
        shots: list[tuple[Shot, ShotTake]],
        *,
        style: Style | None = None,
        outro_key: str | None = None,
        bgm_key: str | None = None,
    ) -> dict[str, Any]:
        return timeline_from_shots(video, shots, style=style, outro_key=outro_key, bgm_key=bgm_key)

    async def render(
        self, timeline: Mapping[str, Any], storage: Storage, output_key: str, thumb_key: str | None = None
    ) -> None:
        await storage.put(output_key, b"", "video/mp4")
        if thumb_key is not None:
            await storage.put(thumb_key, b"", "image/jpeg")

    async def render_outro(self, info: OutroInfo, storage: Storage, key: str) -> None:
        raise NotImplementedError
