"""合成器介面（spec 0007；S13 以 FFmpeg 實作）。"""

from collections.abc import Mapping
from typing import Any, Protocol

from app.domain.ports import Shot, ShotTake, Storage, VideoRecord


class Renderer(Protocol):
    def build_timeline(self, video: VideoRecord, shots: list[tuple[Shot, ShotTake]]) -> dict[str, Any]: ...

    async def render(self, timeline: Mapping[str, Any], storage: Storage, output_key: str) -> None: ...
