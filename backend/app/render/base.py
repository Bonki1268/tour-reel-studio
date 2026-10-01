"""合成器介面（spec 0007；S13 以 FFmpeg 實作，時間軸格式見 timeline.py）。"""

from collections.abc import Mapping
from typing import Any, Protocol

from app.domain.ports import Shot, ShotTake, Storage, VideoRecord
from app.render.timeline import Style


class RenderError(Exception):
    """合成失敗（FFmpeg 錯誤、逾時、素材不存在或輸出不符）；編排據此重試（spec 0013 R-007）。"""


class Renderer(Protocol):
    def build_timeline(
        self,
        video: VideoRecord,
        shots: list[tuple[Shot, ShotTake]],
        *,
        style: Style | None = None,
        outro_key: str | None = None,
        bgm_key: str | None = None,
    ) -> dict[str, Any]: ...

    async def render(
        self, timeline: Mapping[str, Any], storage: Storage, output_key: str, thumb_key: str | None = None
    ) -> None: ...
