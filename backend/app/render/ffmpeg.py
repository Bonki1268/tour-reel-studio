"""FFmpeg 合成器：只依據時間軸 JSON 合成 15 秒 Reels（架構書 §5.6；spec 0013）。

單次 filter_complex：各片段放大填滿後置中裁切為 1080×1920、30fps 並裁成指定長度 → 串接 →
燒錄 ASS 字幕 → 混入 BGM（音量、淡入淡出）→ H.264／AAC。鏡頭片段本身的音訊不使用。
"""

import asyncio
import json
import logging
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from app.config import Settings
from app.domain.ports import Shot, ShotTake, Storage, VideoRecord
from app.render.base import RenderError
from app.render.outro import OutroInfo
from app.render.timeline import Style, Timeline, timeline_from_shots, to_ass
from app.storage.objects import ObjectNotFound

__all__ = ["FONTS_DIR", "FfmpegRenderer", "ProbeResult", "RenderError", "probe"]

FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
DURATION_TOLERANCE_S = 0.25

logger = logging.getLogger(__name__)


def _n(x: float) -> str:
    return f"{x:g}"


def _filter_path(path: Path) -> str:
    """filtergraph 參數中的特殊字元跳脫。"""
    text = str(path)
    for ch in "\\:'[],;":
        text = text.replace(ch, "\\" + ch)
    return text


@dataclass(frozen=True)
class ProbeResult:
    width: int
    height: int
    fps: float
    duration: float
    vcodec: str
    acodec: str | None


async def _run(cmd: list[str], timeout: float) -> bytes:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError as e:
        raise RenderError(f"找不到 {cmd[0]}，請確認已安裝 FFmpeg") from e
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise RenderError(f"{PurePosixPath(cmd[0]).name} 超過 {timeout:g} 秒未完成") from None
    if proc.returncode != 0:
        tail = "\n".join(stderr.decode(errors="replace").strip().splitlines()[-20:])
        raise RenderError(f"{PurePosixPath(cmd[0]).name} 結束代碼 {proc.returncode}：{tail}")
    return stdout


async def probe(path: Path, timeout: float = 30) -> ProbeResult:
    out = await _run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], timeout
    )
    info: dict[str, Any] = json.loads(out)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise RenderError("輸出沒有影像軌")
    audio = next((s for s in info["streams"] if s.get("codec_type") == "audio"), None)
    num, den = (int(x) for x in str(video.get("avg_frame_rate", "0/1")).split("/"))
    return ProbeResult(
        width=int(video["width"]), height=int(video["height"]), fps=num / den if den else 0.0,
        duration=float(info["format"]["duration"]), vcodec=str(video["codec_name"]),
        acodec=str(audio["codec_name"]) if audio else None,
    )


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
        return timeline_from_shots(video, shots, style=style, outro_key=outro_key, bgm_key=bgm_key)

    def command(
        self, timeline: Timeline, inputs: list[Path], bgm: Path | None, ass_path: Path, output_path: Path
    ) -> list[str]:
        """由時間軸組出 FFmpeg 指令（純函式）；inputs 依影片軌片段順序。"""
        out, clips, total = timeline.output, timeline.video_clips, _n(timeline.duration)
        w, h, fps = out.width, out.height, out.fps
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        for path in inputs:
            cmd += ["-i", str(path)]
        if bgm is not None:
            cmd += ["-i", str(bgm)]
        else:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        audio_in = len(inputs)

        parts = []
        for n, clip in enumerate(clips):
            d = _n(clip.duration)
            parts.append(
                f"[{n}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},"
                f"tpad=stop_mode=clone:stop_duration={d},trim=duration={d},setpts=PTS-STARTPTS[v{n}]"
            )
        parts.append("".join(f"[v{n}]" for n in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[vc]")
        parts.append(f"[vc]subtitles={_filter_path(ass_path)}:fontsdir={_filter_path(self.fonts_dir)}[vout]")
        audio = f"[{audio_in}:a]apad,atrim=duration={total},asetpts=PTS-STARTPTS"
        music = timeline.bgm
        if bgm is not None and music is not None:
            fade_out_at = max(timeline.duration - music.fade_out, 0)
            audio += (
                f",volume={_n(music.volume)},afade=t=in:st=0:d={_n(music.fade_in)},"
                f"afade=t=out:st={_n(fade_out_at)}:d={_n(music.fade_out)}"
            )
        parts.append(audio + "[aout]")

        return cmd + [
            "-filter_complex", ";".join(parts),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
            "-t", total, "-movflags", "+faststart", str(output_path),
        ]

    def thumbnail_command(self, video_path: Path, at: float, thumb_path: Path) -> list[str]:
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", _n(at), "-i", str(video_path),
            "-frames:v", "1", "-q:v", "3", str(thumb_path),
        ]

    async def _fetch(self, storage: Storage, key: str, dest: Path) -> Path:
        try:
            dest.write_bytes(await storage.get(key))
        except ObjectNotFound:
            raise RenderError(f"找不到合成素材：{key}") from None
        return dest

    async def render(
        self, timeline: Mapping[str, Any], storage: Storage, output_key: str, thumb_key: str | None = None
    ) -> None:
        try:
            tl = Timeline.model_validate(timeline)
        except ValidationError as e:
            raise RenderError(f"時間軸無效：{e.error_count()} 個錯誤") from None
        started = time.monotonic()
        timeout = self.settings.render_timeout_s
        with tempfile.TemporaryDirectory(prefix="trs-render-") as tmp:
            d = Path(tmp)
            inputs = [
                await self._fetch(storage, c.asset, d / f"in{n}{PurePosixPath(c.asset).suffix or '.mp4'}")
                for n, c in enumerate(tl.video_clips)
            ]
            bgm = None
            if tl.bgm is not None:
                bgm = await self._fetch(storage, tl.bgm.asset, d / f"bgm{PurePosixPath(tl.bgm.asset).suffix}")
            ass_path = d / "subtitles.ass"
            ass_path.write_text(to_ass(tl), encoding="utf-8")
            output = d / "out.mp4"
            await _run(self.command(tl, inputs, bgm, ass_path, output), timeout)

            result = await probe(output)
            expected = (tl.output.width, tl.output.height)
            off = abs(result.duration - tl.duration) > DURATION_TOLERANCE_S
            if (result.width, result.height) != expected or off:
                raise RenderError(
                    f"輸出不符：{result.width}×{result.height}、{result.duration:.2f} 秒"
                    f"（應為 {expected[0]}×{expected[1]}、{tl.duration:g} 秒）"
                )
            await storage.put(output_key, output.read_bytes(), "video/mp4")
            if thumb_key is not None:
                first = tl.video_clips[0]
                thumb = d / "thumb.jpg"
                await _run(self.thumbnail_command(output, first.start + first.duration / 2, thumb), timeout)
                await storage.put(thumb_key, thumb.read_bytes(), "image/jpeg")
        logger.info("合成完成 video_id=%s 長度=%.2f 秒 耗時=%.1f 秒", tl.video_id, result.duration,
                    time.monotonic() - started)

    async def render_outro(self, info: OutroInfo, storage: Storage, key: str) -> None:
        raise NotImplementedError
