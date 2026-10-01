"""FFmpeg 合成器：只依據時間軸 JSON 合成 15 秒 Reels（架構書 §5.6；spec 0013）。"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings
from app.domain.ports import Shot, ShotTake, Storage, VideoRecord
from app.render.timeline import Style, Timeline

FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"


class RenderError(Exception):
    """合成失敗（FFmpeg 錯誤、逾時、素材不存在或輸出不符）。"""


@dataclass(frozen=True)
class ProbeResult:
    width: int
    height: int
    fps: float
    duration: float
    vcodec: str
    acodec: str | None


async def probe(path: Path) -> ProbeResult:
    raise NotImplementedError


class FfmpegRenderer:
    def __init__(self, settings: Settings, fonts_dir: Path = FONTS_DIR) -> None:
        self.settings = settings
        self.fonts_dir = fonts_dir

    def build_timeline(
        self,
        video: VideoRecord,
        shots: list[tuple[Shot, ShotTake]],
        *,
        style: Style | None = None,
        outro_key: str | None = None,
        bgm_key: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def command(
        self, timeline: Timeline, inputs: list[Path], bgm: Path | None, ass_path: Path, output_path: Path
    ) -> list[str]:
        raise NotImplementedError

    def thumbnail_command(self, video_path: Path, at: float, thumb_path: Path) -> list[str]:
        raise NotImplementedError

    async def render(
        self, timeline: Mapping[str, Any], storage: Storage, output_key: str, thumb_key: str | None = None
    ) -> None:
        raise NotImplementedError
