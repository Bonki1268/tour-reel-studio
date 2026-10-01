"""FakeRenderer：只產生時間軸 JSON 與空白成品檔（spec 0007）。"""

from collections.abc import Mapping
from typing import Any

from app.domain.ports import Shot, ShotTake, Storage, VideoRecord
from app.render.timeline import Style


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
        clips = []
        start = 0.0
        for shot, take in shots:
            end = start + shot.duration_s
            subtitle = (shot.prompt or {}).get("subtitle", "")
            clips.append({"shot_no": shot.shot_no, "clip_key": take.clip_key, "start": start, "end": end,
                          "subtitle": subtitle})
            start = end
        return {"version": 1, "video_id": video.id, "duration_s": start, "clips": clips}

    async def render(
        self, timeline: Mapping[str, Any], storage: Storage, output_key: str, thumb_key: str | None = None
    ) -> None:
        await storage.put(output_key, b"", "video/mp4")
