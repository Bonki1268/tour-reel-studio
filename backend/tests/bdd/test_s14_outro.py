import asyncio
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, scenarios, then, when

from app.config import Settings
from app.render.ffmpeg import FfmpegRenderer
from app.render.outro import OutroInfo, make_card, parse_color
from app.storage.objects import MemoryStorage
from tests.outro_support import blue_pixels, decode_qr, make_logo
from tests.render_support import ffprobe

pytestmark = pytest.mark.S14

# 自動產生的名稱 test_s1404_片尾卡轉為_3_秒影片段 經閘門正規化（去掉中文）後，編號緊接數字 3 而無法比對；
# 改以明確名稱綁定
@scenario("api/s14_outro.feature", "S14-04 片尾卡轉為 3 秒影片段")
def test_s1404_outro_clip() -> None:
    pass


scenarios("api/s14_outro.feature")

OUTRO_KEY = "videos/v1/outro.mp4"


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {"logo": None}


@given(parsers.parse('品牌主色為 "{color}"、店名為 "{name}"、地址為 "{address}"'))
def brand(ctx: dict[str, Any], color: str, name: str, address: str) -> None:
    ctx.update(color=color, name=name, address=address)


@given(parsers.parse('訂位網址為 "{url}"'))
def booking(ctx: dict[str, Any], url: str) -> None:
    ctx["url"] = url


@given("品牌檔案有 Logo")
def with_logo(ctx: dict[str, Any]) -> None:
    ctx["logo"] = make_logo()


@given("品牌檔案沒有 Logo")
def without_logo(ctx: dict[str, Any]) -> None:
    ctx["logo"] = None


def _info(ctx: dict[str, Any]) -> OutroInfo:
    return OutroInfo(
        name=ctx["name"],
        address=ctx["address"],
        primary_color=ctx["color"],
        booking_url=ctx["url"],
        logo=ctx["logo"],
    )


@when("產生片尾卡")
def card(ctx: dict[str, Any]) -> None:
    ctx["card"] = make_card(_info(ctx))


# S14-01


@then(parsers.parse("片尾卡尺寸為 {w:d}×{h:d}"))
def card_size(ctx: dict[str, Any], w: int, h: int) -> None:
    assert ctx["card"].image.size == (w, h)


@then(parsers.parse('背景主要顏色接近 "{color}"'))
def background(ctx: dict[str, Any], color: str) -> None:
    image = ctx["card"].image.convert("RGB")
    samples = [(5, 5), (1074, 5), (5, 1914), (1074, 1914), (540, 100), (540, 1850), (20, 960), (1060, 960)]
    pixels = [image.getpixel(p) for p in samples]
    expected = parse_color(color)
    for channel in range(3):
        mean = sum(px[channel] for px in pixels) / len(pixels)
        assert abs(mean - expected[channel]) <= 8


@then("片尾卡包含 Logo")
def has_logo(ctx: dict[str, Any]) -> None:
    assert "logo" in ctx["card"].layers
    assert blue_pixels(ctx["card"]) > 1000


# S14-02


@then(parsers.parse('片尾卡上的 QR code 解碼為 "{url}"'))
def qr(ctx: dict[str, Any], url: str) -> None:
    assert "qr" in ctx["card"].layers
    assert decode_qr(ctx["card"]) == url
    left, top, right, bottom = ctx["card"].boxes["qr"]
    assert right - left >= 360 and bottom - top >= 360


# S14-03


@then("產生成功且不包含 Logo 圖層")
def no_logo(ctx: dict[str, Any]) -> None:
    layers = ctx["card"].layers
    assert "logo" not in layers and "name" in layers
    assert blue_pixels(ctx["card"]) == 0


# S14-04


@when("產生片尾影片段")
def clip(ctx: dict[str, Any]) -> None:
    storage = MemoryStorage()
    asyncio.run(FfmpegRenderer(Settings()).render_outro(_info(ctx), storage, OUTRO_KEY))
    ctx["probe"] = ffprobe(asyncio.run(storage.get(OUTRO_KEY)))


@then(parsers.parse("影片段長度為 {seconds:g} ± {tol:g} 秒"))
def clip_duration(ctx: dict[str, Any], seconds: float, tol: float) -> None:
    assert abs(ctx["probe"].duration - seconds) <= tol


@then(parsers.parse("影片段為 {w:d}×{h:d}、{fps:d}fps"))
def clip_format(ctx: dict[str, Any], w: int, h: int, fps: int) -> None:
    p = ctx["probe"]
    assert (p.width, p.height) == (w, h)
    assert abs(p.fps - fps) < 0.01
    assert p.vcodec == "h264"
