"""時間軸 JSON：合成的唯一依據（構想文件 §5.3；架構書 §5.6；spec 0013）。"""

from typing import Literal

from pydantic import BaseModel, Field

DEFAULT_COLOR = "#C8553D"
FONT = "Noto Sans TC"
OUTRO_DURATION = 3.0
BGM_VOLUME = 0.3


class Output(BaseModel):
    aspect_ratio: str = "9:16"
    width: int = 1080
    height: int = 1920
    fps: int = 30
    subtitle_lang: str = "zh-TW"


class Style(BaseModel):
    primary_color: str = DEFAULT_COLOR
    font: str = FONT


class VideoClip(BaseModel):
    shot_no: int | None = None
    asset: str
    source: Literal["ai_composite", "ai_generated", "real_footage", "template"]
    provider: str | None = None
    start: float = Field(ge=0)
    duration: float = Field(gt=0)


class SubtitleItem(BaseModel):
    text: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class AudioClip(BaseModel):
    asset: str
    start: float = 0
    volume: float = Field(default=BGM_VOLUME, ge=0, le=1)
    fade_in: float = Field(default=0.5, ge=0)
    fade_out: float = Field(default=1.0, ge=0)


class VideoTrack(BaseModel):
    type: Literal["video"] = "video"
    clips: list[VideoClip]


class SubtitleTrack(BaseModel):
    type: Literal["subtitle"] = "subtitle"
    items: list[SubtitleItem] = []


class AudioTrack(BaseModel):
    type: Literal["audio"] = "audio"
    clips: list[AudioClip] = []


class Timeline(BaseModel):
    version: int = 1
    project_id: str
    video_id: str
    duration: float
    output: Output = Output()
    style: Style = Style()
    tracks: list[VideoTrack | SubtitleTrack | AudioTrack]

    @property
    def video_clips(self) -> list[VideoClip]:
        raise NotImplementedError

    @property
    def subtitles(self) -> list[SubtitleItem]:
        raise NotImplementedError

    @property
    def bgm(self) -> AudioClip | None:
        raise NotImplementedError


class ShotResult(BaseModel):
    shot_no: int
    clip_key: str
    duration: float
    subtitle: str = ""


def build_timeline(
    *,
    project_id: str,
    video_id: str,
    shots: list[ShotResult],
    outro_key: str | None = None,
    bgm_key: str | None = None,
    style: Style | None = None,
) -> Timeline:
    raise NotImplementedError


def set_clip_duration(timeline: Timeline, index: int, seconds: float) -> Timeline:
    """修改第 index（0 起算）段的長度，後續片段與字幕順延；回傳新的時間軸。"""
    raise NotImplementedError


def ass_time(seconds: float) -> str:
    raise NotImplementedError


def to_ass(timeline: Timeline) -> str:
    raise NotImplementedError
