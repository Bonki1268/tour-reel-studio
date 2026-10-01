"""S13 測試共用：以 FFmpeg 即時產生測試片段與 BGM，並以 ffprobe／volumedetect 量測輸出。"""

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from app.render.timeline import ShotResult, Style, Timeline, build_timeline
from app.storage.objects import MemoryStorage

PROJECT_ID = "p1"
VIDEO_ID = "v1"
PRIMARY = "#C8553D"
SHOT_DURATIONS = (4.0, 5.0, 3.0)
SHOT_SIZES = ((720, 1280), (1280, 720), (640, 640))  # 不同尺寸
SUBTITLES = ("1661 年，我來過這！", "古堡拿鐵，好喝！", "來古堡喝一杯吧！")
OUTRO_KEY = "videos/v1/outro.mp4"
BGM_KEY = "assets/bgm/test-bgm.wav"


def clip_key(n: int) -> str:
    return f"videos/v1/shots/{n}/take1/clip.mp4"


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@cache
def make_clip(width: int, height: int, seconds: float, fps: int = 24) -> bytes:
    """testsrc 片段（含一條音軌，用來驗證鏡頭音訊不被使用）。"""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "clip.mp4"
        _ffmpeg(
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={width}x{height}:rate={fps}:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1000:duration={seconds}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out),
        )
        return out.read_bytes()


@cache
def make_bgm(seconds: float = 20.0) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "bgm.wav"
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-ac", "2", str(out))
        return out.read_bytes()


async def seeded_storage(with_bgm: bool = True) -> MemoryStorage:
    """3 段 24fps、不同尺寸的 4 秒片段（第 2 段比時間軸短、第 3 段比時間軸長）、3 秒片尾與 BGM。"""
    storage = MemoryStorage()
    for n, (w, h) in enumerate(SHOT_SIZES, start=1):
        await storage.put(clip_key(n), make_clip(w, h, 4.0), "video/mp4")
    await storage.put(OUTRO_KEY, make_clip(1080, 1920, 3.0, fps=30), "video/mp4")
    if with_bgm:
        await storage.put(BGM_KEY, make_bgm(), "audio/wav")
    return storage


def shot_results() -> list[ShotResult]:
    return [
        ShotResult(shot_no=n, clip_key=clip_key(n), duration=d, subtitle=s)
        for n, (d, s) in enumerate(zip(SHOT_DURATIONS, SUBTITLES, strict=True), start=1)
    ]


def sample_timeline(*, bgm: bool = True, outro: bool = True) -> Timeline:
    return build_timeline(
        project_id=PROJECT_ID,
        video_id=VIDEO_ID,
        shots=shot_results(),
        outro_key=OUTRO_KEY if outro else None,
        bgm_key=BGM_KEY if bgm else None,
        style=Style(primary_color=PRIMARY),
    )


@dataclass(frozen=True)
class Probe:
    width: int
    height: int
    fps: float
    duration: float
    vcodec: str
    acodec: str | None


def ffprobe(data: bytes, suffix: str = ".mp4") -> Probe:
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", f.name],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    info: dict[str, Any] = json.loads(out)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    num, den = (int(x) for x in video["avg_frame_rate"].split("/"))
    return Probe(
        width=int(video["width"]),
        height=int(video["height"]),
        fps=num / den if den else 0.0,
        duration=float(info["format"]["duration"]),
        vcodec=video["codec_name"],
        acodec=audio["codec_name"] if audio else None,
    )


def mean_volume(data: bytes, start: float, duration: float) -> float:
    """指定區間的平均音量（dB）。"""
    with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
        f.write(data)
        f.flush()
        err = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-ss",
                str(start),
                "-t",
                str(duration),
                "-i",
                f.name,
                "-af",
                "volumedetect",
                "-vn",
                "-f",
                "null",
                "-",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stderr
    match = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", err)
    assert match, err
    return float("-inf") if match.group(1) == "-inf" else float(match.group(1))
