import asyncio
import hashlib
import io
import json
import re
from typing import Any

import pytest
from PIL import Image
from pytest_bdd import given, parsers, scenario, scenarios, then, when

from app.config import Settings
from app.render.ffmpeg import FfmpegRenderer
from app.render.timeline import Timeline, ass_time, set_clip_duration, to_ass
from tests.render_support import (
    PRIMARY,
    ffprobe,
    mean_volume,
    sample_timeline,
    seeded_storage,
)

pytestmark = pytest.mark.S13

# 自動產生的名稱 test_s1302_合成_15_秒直式影片 經閘門正規化（去掉中文）後，編號緊接數字 15 而無法比對；
# 改以明確名稱綁定
@scenario("api/s13_render.feature", "S13-02 合成 15 秒直式影片")
def test_s1302_render_vertical_video() -> None:
    pass


scenarios("api/s13_render.feature")

OUTPUT_KEY = "videos/v1/renders/r1.mp4"
THUMB_KEY = "videos/v1/renders/r1.jpg"

# 相同時間軸只合成一次（S13-02、04、06 共用）
_RENDERED: dict[str, tuple[bytes, bytes]] = {}


def run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {}


def _render(timeline: Timeline) -> tuple[bytes, bytes]:
    data = timeline.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if digest not in _RENDERED:
        storage = run(seeded_storage())
        run(FfmpegRenderer(Settings()).render(data, storage, OUTPUT_KEY, THUMB_KEY))
        _RENDERED[digest] = (run(storage.get(OUTPUT_KEY)), run(storage.get(THUMB_KEY)))
    return _RENDERED[digest]


# S13-01


@given("3 個長度分別為 4、5、3 秒的鏡頭結果與 3 秒片尾")
def shot_results_given(ctx: dict[str, Any]) -> None:
    ctx["build"] = sample_timeline


@when("組出時間軸 JSON")
def build_json(ctx: dict[str, Any]) -> None:
    timeline: Timeline = ctx["build"]()
    ctx["json"] = json.loads(json.dumps(timeline.model_dump(mode="json")))


def _video_clips(data: dict[str, Any]) -> list[dict[str, Any]]:
    track = next(t for t in data["tracks"] if t["type"] == "video")
    return list(track["clips"])


@then("影片軌的片段起點依序為 0、4、9、12 秒")
def clip_starts(ctx: dict[str, Any]) -> None:
    clips = _video_clips(ctx["json"])
    assert [c["start"] for c in clips] == [0, 4, 9, 12]
    assert [c["source"] for c in clips] == ["ai_composite"] * 3 + ["template"]


@then("總長度為 15 秒")
def total(ctx: dict[str, Any]) -> None:
    assert ctx["json"]["duration"] == 15
    last = _video_clips(ctx["json"])[-1]
    assert last["start"] + last["duration"] == 15


@then("每個片段都有 source 欄位")
def has_source(ctx: dict[str, Any]) -> None:
    clips = _video_clips(ctx["json"])
    assert all(c.get("source") and c.get("asset") for c in clips)
    assert Timeline.model_validate(ctx["json"]).duration == 15


# S13-02、S13-04、S13-06


@given("3 段不同尺寸、24fps 的測試影片與一首 BGM")
def media_given(ctx: dict[str, Any]) -> None:
    ctx["timeline"] = sample_timeline()


@when("依時間軸 JSON 合成")
def render(ctx: dict[str, Any]) -> None:
    timeline = ctx.get("timeline") or sample_timeline()
    ctx["mp4"], ctx["thumb"] = _render(timeline)
    ctx["probe"] = ffprobe(ctx["mp4"])


@then(parsers.parse("輸出影片為 {w:d}×{h:d}"))
def size(ctx: dict[str, Any], w: int, h: int) -> None:
    assert (ctx["probe"].width, ctx["probe"].height) == (w, h)


@then(parsers.parse("輸出影片為 {fps:d}fps"))
def fps(ctx: dict[str, Any], fps: int) -> None:
    assert abs(ctx["probe"].fps - fps) < 0.01


@then(parsers.parse("輸出影片長度為 {seconds:g} ± {tol:g} 秒"))
def duration(ctx: dict[str, Any], seconds: float, tol: float) -> None:
    assert abs(ctx["probe"].duration - seconds) <= tol


@then("影像編碼為 H.264、音訊編碼為 AAC")
def codecs(ctx: dict[str, Any]) -> None:
    assert ctx["probe"].vcodec == "h264"
    assert ctx["probe"].acodec == "aac"


# S13-03


@given("一份含 3 段字幕的時間軸 JSON")
def timeline_with_subtitles(ctx: dict[str, Any]) -> None:
    ctx["timeline"] = sample_timeline()
    assert len(ctx["timeline"].subtitles) == 3


@when("產生 ASS 字幕檔")
def make_ass(ctx: dict[str, Any]) -> None:
    ctx["ass"] = to_ass(ctx["timeline"])


@then("字幕檔包含 3 段字幕且時間與時間軸一致")
def ass_events(ctx: dict[str, Any]) -> None:
    lines = [ln for ln in ctx["ass"].splitlines() if ln.startswith("Dialogue:")]
    assert len(lines) == 3
    for line, item in zip(lines, ctx["timeline"].subtitles, strict=True):
        fields = line.split(",", 9)
        assert fields[1] == ass_time(item.start)
        assert fields[2] == ass_time(item.end)
        assert fields[9] == item.text
    assert re.search(r"^PlayResY:\s*1920$", ctx["ass"], re.M)


@then(parsers.parse('字幕字型為 "{font}"'))
def ass_font(ctx: dict[str, Any], font: str) -> None:
    style = next(ln for ln in ctx["ass"].splitlines() if ln.startswith("Style:"))
    fields = style.split(":", 1)[1].split(",")
    assert fields[1].strip() == font
    r, g, b = PRIMARY[1:3], PRIMARY[3:5], PRIMARY[5:7]
    assert fields[5].strip().upper() == f"&H00{b}{g}{r}".upper()  # 描邊為品牌主色


# S13-04


@then("輸出影片有音軌")
def has_audio(ctx: dict[str, Any]) -> None:
    assert ctx["probe"].acodec == "aac"


@then("開頭 0.3 秒的平均音量低於中段")
def fade_in(ctx: dict[str, Any]) -> None:
    head = mean_volume(ctx["mp4"], 0, 0.3)
    middle = mean_volume(ctx["mp4"], 6, 3)
    assert head < middle - 3


# S13-05


@given("將時間軸中第 2 段的長度改為 3 秒")
def shorten_second(ctx: dict[str, Any]) -> None:
    ctx["timeline"] = set_clip_duration(sample_timeline(), 1, 3)


# S13-06


@then(parsers.parse("產生一張 {w:d}×{h:d} 的縮圖"))
def thumbnail(ctx: dict[str, Any], w: int, h: int) -> None:
    image = Image.open(io.BytesIO(ctx["thumb"]))
    assert image.format == "JPEG"
    assert image.size == (w, h)
