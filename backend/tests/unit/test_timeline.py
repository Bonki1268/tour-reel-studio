"""時間軸 JSON 與 ASS 字幕（spec 0013）。"""

from typing import Any

import pytest
from pydantic import ValidationError

from app.render.timeline import Style, Timeline, ass_time, build_timeline, set_clip_duration, to_ass
from tests.render_support import OUTRO_KEY, sample_timeline, shot_results

pytestmark = pytest.mark.S13


# R-001


def test_r001_clips_contiguous_from_zero() -> None:
    t = sample_timeline()
    clips = t.video_clips
    assert clips[0].start == 0
    for a, b in zip(clips, clips[1:], strict=False):
        assert b.start == pytest.approx(a.start + a.duration)
    assert t.duration == pytest.approx(clips[-1].start + clips[-1].duration)
    assert [c.shot_no for c in clips] == [1, 2, 3, None]
    assert clips[-1].asset == OUTRO_KEY
    assert all(c.provider == "higgsfield" for c in clips[:3])


def _mutate(edit: str) -> dict[str, Any]:
    data = sample_timeline().model_dump(mode="json")
    clips = next(t for t in data["tracks"] if t["type"] == "video")["clips"]
    if edit == "gap":
        clips[1]["start"] += 0.5
    elif edit == "overlap":
        clips[2]["start"] -= 0.5
    elif edit == "wrong_total":
        data["duration"] = 14
    elif edit == "not_from_zero":
        for c in clips:
            c["start"] += 1
        data["duration"] += 1
    elif edit == "subtitle_outside":
        next(t for t in data["tracks"] if t["type"] == "subtitle")["items"][0]["end"] = 99
    return data


@pytest.mark.parametrize("edit", ["gap", "overlap", "wrong_total", "not_from_zero", "subtitle_outside"])
def test_r001_rejects_gap_or_overlap(edit: str) -> None:
    with pytest.raises(ValidationError):
        Timeline.model_validate(_mutate(edit))


def test_r001_subtitles_inside_shot() -> None:
    t = sample_timeline()
    assert [s.text for s in t.subtitles] == [r.subtitle for r in shot_results()]
    for item, clip in zip(t.subtitles, t.video_clips, strict=False):
        assert clip.start <= item.start < item.end <= clip.start + clip.duration
        assert item.start == pytest.approx(clip.start + 0.3)
        assert item.end == pytest.approx(clip.start + clip.duration - 0.2)


def test_r001_without_outro_and_bgm() -> None:
    t = sample_timeline(outro=False, bgm=False)
    assert t.duration == 12
    assert len(t.video_clips) == 3
    assert t.bgm is None


def test_r001_bgm_track_defaults() -> None:
    bgm = sample_timeline().bgm
    assert bgm is not None
    assert (bgm.volume, bgm.start) == (0.3, 0)


def test_r001_empty_subtitle_skipped() -> None:
    shots = shot_results()
    shots[1] = shots[1].model_copy(update={"subtitle": "  "})
    t = build_timeline(project_id="p", video_id="v", shots=shots)
    assert len(t.subtitles) == 2


def test_r001_style_and_output() -> None:
    t = build_timeline(
        project_id="p", video_id="v", shots=shot_results(), style=Style(primary_color="#123456")
    )
    assert t.style.primary_color == "#123456" and t.style.font == "Noto Sans TC"
    assert (t.output.width, t.output.height, t.output.fps) == (1080, 1920, 30)


# R-003


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "0:00:00.00"),
        (0.3, "0:00:00.30"),
        (12.345, "0:00:12.35"),
        (61.5, "0:01:01.50"),
        (3725.0, "1:02:05.00"),
    ],
)
def test_r003_ass_time_format(seconds: float, text: str) -> None:
    assert ass_time(seconds) == text


def test_r003_ass_style_font_and_outline() -> None:
    ass = to_ass(sample_timeline())
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    style = next(ln for ln in ass.splitlines() if ln.startswith("Style:"))
    fields = [f.strip() for f in style.split(":", 1)[1].split(",")]
    assert fields[1] == "Noto Sans TC"
    assert fields[5] == "&H003D55C8"  # #C8553D → BGR
    assert fields[18] == "2"  # 下方置中
    assert int(fields[21]) >= 384  # 底邊距在安全區內（1920 的 20%）


def test_r003_ass_escapes_text() -> None:
    shots = shot_results()
    shots[0] = shots[0].model_copy(update={"subtitle": "{\\b1}粗體\n第二行"})
    ass = to_ass(build_timeline(project_id="p", video_id="v", shots=shots))
    line = next(ln for ln in ass.splitlines() if ln.startswith("Dialogue:"))
    text = line.split(",", 9)[9]
    assert text == "\\{\\\\b1\\}粗體\\N第二行"


# R-005


def test_r005_set_clip_duration_shifts_following() -> None:
    original = sample_timeline()
    t = set_clip_duration(original, 1, 3)
    assert [c.start for c in t.video_clips] == [0, 4, 7, 10]
    assert t.duration == 13
    assert t.subtitles[2].start == pytest.approx(original.subtitles[2].start - 2)
    assert t.subtitles[1].end == pytest.approx(4 + 3 - 0.2)
    assert original.duration == 15  # 原時間軸不變
    Timeline.model_validate(t.model_dump(mode="json"))


@pytest.mark.parametrize(("index", "seconds"), [(1, 0), (1, -1), (9, 3)])
def test_r005_set_clip_duration_rejects_invalid(index: int, seconds: float) -> None:
    with pytest.raises((ValueError, IndexError)):
        set_clip_duration(sample_timeline(), index, seconds)
