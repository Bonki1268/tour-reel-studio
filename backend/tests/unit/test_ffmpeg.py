"""FFmpeg 指令組裝（不執行）與合成失敗（spec 0013）。"""

from pathlib import Path

import pytest

from app.config import Settings
from app.render.ffmpeg import FONTS_DIR, FfmpegRenderer, RenderError
from app.storage.objects import MemoryStorage
from tests.render_support import sample_timeline

pytestmark = pytest.mark.S13

INPUTS = [Path(f"/tmp/r/in{n}.mp4") for n in range(4)]
BGM = Path("/tmp/r/bgm.wav")
ASS = Path("/tmp/r/subs.ass")
OUT = Path("/tmp/r/out.mp4")


def _cmd(bgm: Path | None = BGM) -> list[str]:
    return FfmpegRenderer(Settings()).command(sample_timeline(bgm=bgm is not None), INPUTS, bgm, ASS, OUT)


def _graph(cmd: list[str]) -> str:
    return cmd[cmd.index("-filter_complex") + 1]


# R-002


def test_r002_command_has_scale_crop_fps_codecs() -> None:
    cmd = _cmd()
    graph = _graph(cmd)
    assert graph.count("scale=1080:1920:force_original_aspect_ratio=increase") == 4
    assert graph.count("crop=1080:1920") == 4
    assert graph.count("fps=30") == 4
    assert "concat=n=4:v=1:a=0" in graph
    assert f"subtitles={ASS}" in graph and f"fontsdir={FONTS_DIR}" in graph
    for flag, value in [
        ("-c:v", "libx264"),
        ("-pix_fmt", "yuv420p"),
        ("-c:a", "aac"),
        ("-r", "30"),
        ("-t", "15"),
    ]:
        assert cmd[cmd.index(flag) + 1] == value
    assert cmd[-1] == str(OUT)
    for path in INPUTS:
        assert str(path) in cmd


def test_r002_command_trims_and_pads_each_clip() -> None:
    graph = _graph(_cmd())
    for seconds in ("4", "5", "3"):
        assert f"trim=duration={seconds}" in graph
    assert graph.count("tpad=stop_mode=clone") == 4


def test_r002_command_ignores_clip_audio() -> None:
    cmd = _cmd()
    graph = _graph(cmd)
    for n in range(4):
        assert f"[{n}:a]" not in graph
    maps = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-map"]
    assert maps == ["[vout]", "[aout]"]


# R-004


def test_r004_command_bgm_volume_and_fades() -> None:
    graph = _graph(_cmd())
    assert "[4:a]" in graph
    assert "volume=0.3" in graph
    assert "afade=t=in:st=0:d=0.5" in graph
    assert "afade=t=out:st=14:d=1" in graph
    assert "atrim=duration=15" in graph


def test_r004_silent_track_without_bgm() -> None:
    cmd = _cmd(bgm=None)
    assert "anullsrc=r=48000:cl=stereo" in " ".join(cmd)
    assert "volume=0.3" not in _graph(cmd)
    assert cmd[cmd.index("-map", cmd.index("-map") + 1) + 1] == "[aout]"


# R-006


def test_r006_thumbnail_command() -> None:
    cmd = FfmpegRenderer(Settings()).thumbnail_command(OUT, 2.0, Path("/tmp/r/t.jpg"))
    assert cmd[cmd.index("-ss") + 1] == "2"
    assert cmd[cmd.index("-frames:v") + 1] == "1"
    assert cmd[-1] == "/tmp/r/t.jpg"


# R-007


async def test_r007_missing_asset_raises_render_error() -> None:
    renderer = FfmpegRenderer(Settings())
    with pytest.raises(RenderError):
        await renderer.render(
            sample_timeline().model_dump(mode="json"), MemoryStorage(), "out.mp4", "out.jpg"
        )


async def test_r007_invalid_timeline_raises_render_error() -> None:
    with pytest.raises(RenderError):
        await FfmpegRenderer(Settings()).render({"tracks": []}, MemoryStorage(), "out.mp4")
