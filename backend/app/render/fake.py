"""FakeRenderer：只產生時間軸 JSON 與空白成品檔（spec 0007）。"""

from collections.abc import Mapping
from typing import Any

from app.domain.ports import Shot, ShotTake, Storage, VideoRecord


class FakeRenderer:
    def build_timeline(self, video: VideoRecord, shots: list[tuple[Shot, ShotTake]]) -> dict[str, Any]:
        raise NotImplementedError

    async def render(self, timeline: Mapping[str, Any], storage: Storage, output_key: str) -> None:
        raise NotImplementedError
