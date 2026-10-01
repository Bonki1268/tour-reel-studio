"""時間軸 JSON：合成的唯一依據（構想文件 §5.3；架構書 §5.6；spec 0013）。"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.domain.ports import Shot, ShotTake, VideoRecord

DEFAULT_COLOR = "#C8553D"
FONT = "Noto Sans TC"
OUTRO_DURATION = 3.0
BGM_VOLUME = 0.3
SUBTITLE_LEAD_S = 0.3  # 字幕從鏡頭起點後 0.3 秒出現（構想文件 §5.3 範例）
SUBTITLE_TAIL_S = 0.2  # 鏡頭結束前 0.2 秒消失
EPS = 1e-3


def _r(x: float) -> float:
    return round(x, 3)


class Output(BaseModel):
    aspect_ratio: str = "9:16"
    width: int = 1080
    height: int = 1920
    fps: int = 30
    subtitle_lang: str = "zh-TW"


class Style(BaseModel):
    primary_color: str = Field(default=DEFAULT_COLOR, pattern=r"^#[0-9A-Fa-f]{6}$")
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

    @model_validator(mode="after")
    def _check(self) -> Self:
        if [t.type for t in self.tracks].count("video") != 1:
            raise ValueError("時間軸必須有且只有一條影片軌")
        clips = self.video_clips
        if not clips:
            raise ValueError("影片軌沒有片段")
        end = 0.0
        for n, clip in enumerate(clips, start=1):
            if abs(clip.start - end) > EPS:
                raise ValueError(f"第 {n} 段起點 {clip.start:g} 秒，應接在 {end:g} 秒（片段須連續且不重疊）")
            end = clip.start + clip.duration
        if abs(self.duration - end) > EPS:
            raise ValueError(f"總長度 {self.duration:g} 秒與影片軌結束時間 {end:g} 秒不符")
        for item in self.subtitles:
            if not (0 <= item.start < item.end <= self.duration + EPS):
                raise ValueError(f"字幕「{item.text}」的時間超出影片範圍")
        return self

    def _track(self, kind: str) -> Any:
        return next((t for t in self.tracks if t.type == kind), None)

    @property
    def video_clips(self) -> list[VideoClip]:
        track = self._track("video")
        return list(track.clips) if track else []

    @property
    def subtitles(self) -> list[SubtitleItem]:
        track = self._track("subtitle")
        return list(track.items) if track else []

    @property
    def bgm(self) -> AudioClip | None:
        track = self._track("audio")
        return track.clips[0] if track and track.clips else None


class ShotResult(BaseModel):
    shot_no: int
    clip_key: str
    duration: float
    subtitle: str = ""


def _subtitle(text: str, start: float, duration: float) -> SubtitleItem | None:
    text = text.strip()
    if not text:
        return None
    lead = SUBTITLE_LEAD_S if duration > 1 else 0.0
    tail = SUBTITLE_TAIL_S if duration > 1 else 0.0
    return SubtitleItem(text=text, start=_r(start + lead), end=_r(start + duration - tail))


def build_timeline(
    *,
    project_id: str,
    video_id: str,
    shots: list[ShotResult],
    outro_key: str | None = None,
    bgm_key: str | None = None,
    style: Style | None = None,
) -> Timeline:
    """鏡頭依序首尾相接，最後接片尾；每鏡一段字幕（片尾不加）；BGM 音量 0.3。"""
    clips: list[VideoClip] = []
    items: list[SubtitleItem] = []
    start = 0.0
    for shot in shots:
        clips.append(VideoClip(shot_no=shot.shot_no, asset=shot.clip_key, source="ai_composite",
                               provider="higgsfield", start=_r(start), duration=shot.duration))
        if (item := _subtitle(shot.subtitle, start, shot.duration)) is not None:
            items.append(item)
        start += shot.duration
    if outro_key:
        clips.append(VideoClip(asset=outro_key, source="template", start=_r(start), duration=OUTRO_DURATION))
        start += OUTRO_DURATION
    audio = [AudioClip(asset=bgm_key)] if bgm_key else []
    return Timeline(
        project_id=project_id, video_id=video_id, duration=_r(start), style=style or Style(),
        tracks=[VideoTrack(clips=clips), SubtitleTrack(items=items), AudioTrack(clips=audio)],
    )


def timeline_from_shots(
    video: VideoRecord,
    shots: list[tuple[Shot, ShotTake]],
    *,
    style: Style | None = None,
    outro_key: str | None = None,
    bgm_key: str | None = None,
) -> dict[str, Any]:
    """Renderer.build_timeline 的共用實作：由鏡頭紀錄組出時間軸 JSON。"""
    results = [
        ShotResult(shot_no=s.shot_no, clip_key=t.clip_key or "", duration=s.duration_s,
                   subtitle=str((s.prompt or {}).get("subtitle", "")))
        for s, t in shots
    ]
    timeline = build_timeline(project_id=video.project_id, video_id=video.id, shots=results,
                              outro_key=outro_key, bgm_key=bgm_key, style=style)
    return timeline.model_dump(mode="json")


def set_clip_duration(timeline: Timeline, index: int, seconds: float) -> Timeline:
    """修改第 index（0 起算）段的長度，後續片段與字幕順延；回傳新的時間軸（時間軸編輯器的基本操作）。"""
    if seconds <= 0:
        raise ValueError("片段長度必須大於 0")
    clips = timeline.video_clips
    if not 0 <= index < len(clips):
        raise IndexError(f"沒有第 {index} 段")
    target = clips[index]
    old_end = target.start + target.duration
    new_end = target.start + seconds
    delta = seconds - target.duration
    data = timeline.model_dump(mode="json")
    for track in data["tracks"]:
        if track["type"] == "video":
            for n, clip in enumerate(track["clips"]):
                if n == index:
                    clip["duration"] = seconds
                elif n > index:
                    clip["start"] = _r(clip["start"] + delta)
        elif track["type"] == "subtitle":
            for item in track["items"]:
                if item["start"] >= old_end - EPS:
                    item["start"], item["end"] = _r(item["start"] + delta), _r(item["end"] + delta)
                elif item["end"] > target.start:  # 該段內的字幕：結束時間隨之調整，且不超過新的結束點
                    item["end"] = _r(max(item["start"] + 0.1, min(item["end"] + delta, new_end)))
    data["duration"] = _r(timeline.duration + delta)
    return Timeline.model_validate(data)


def ass_time(seconds: float) -> str:
    """秒 → ASS 時間 H:MM:SS.cc（四捨五入到百分之一秒）。"""
    cs = int((Decimal(str(seconds)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_color(hex_color: str) -> str:
    """#RRGGBB → ASS &H00BBGGRR。"""
    r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"&H00{b}{g}{r}".upper()


def _escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            .replace("\r\n", "\\N").replace("\n", "\\N"))


def to_ass(timeline: Timeline) -> str:
    """字幕置於下方安全區：底邊距 400 px（1920 高）、字級 72、粗體、品牌主色描邊。"""
    out, style = timeline.output, timeline.style
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {out.width}",
        f"PlayResY: {out.height}",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{style.font},72,&H00FFFFFF,&H00FFFFFF,{ass_color(style.primary_color)},&H64000000,"
        "-1,0,0,0,100,100,0,0,1,5,0,2,60,60,400,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for item in timeline.subtitles:
        start, end = ass_time(item.start), ass_time(item.end)
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{_escape(item.text)}")
    return "\n".join(lines) + "\n"
