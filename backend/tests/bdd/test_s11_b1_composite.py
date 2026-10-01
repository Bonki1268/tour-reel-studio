import socket
from typing import Any, cast

import pytest
from PIL import ImageChops, ImageOps
from pytest_bdd import given, parsers, scenarios, then, when

from app.providers.composite import (
    Placement,
    PlacementError,
    build_compose_request,
    composite,
    to_png,
)
from tests.composite_support import feet_center, make_cutout, make_photo, mask_bbox

pytestmark = pytest.mark.S11

scenarios("api/s11_b1_composite.feature")

ROUGH_KEY = "videos/v1/shots/1/take1/rough.png"
MASK_KEY = "videos/v1/shots/1/take1/mask.png"
BOARD_KEY = "projects/p1/characters/c1/v1/identity_board.png"
KEYFRAME_PROMPT = "A smiling guide waves on the old street at golden hour"


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {}


def _place(ctx: dict[str, Any], x: float, y: float, scale: float, flip: bool = False) -> None:
    try:
        ctx["result"] = composite(ctx["photo"], ctx["cutout"], Placement(x, y, scale, flip))
    except PlacementError as e:
        ctx["error"] = e


@given("一張 1000×1500 的實景照")
def photo(ctx: dict[str, Any]) -> None:
    ctx["photo"] = make_photo((1000, 1500))


@given("一張 400×800、背景透明的角色去背圖")
def cutout(ctx: dict[str, Any]) -> None:
    ctx["cutout"] = make_cutout()


@when(parsers.parse("以 x={x:g}、y={y:g}、scale={scale:g} 合成"))
def place(ctx: dict[str, Any], x: float, y: float, scale: float) -> None:
    _place(ctx, x, y, scale)


@when(parsers.parse("以 x={x:g}、y={y:g}、scale={scale:g}、flip=true 合成"))
def place_flipped(ctx: dict[str, Any], x: float, y: float, scale: float) -> None:
    ctx["unflipped"] = composite(ctx["photo"], ctx["cutout"], Placement(x, y, scale))
    _place(ctx, x, y, scale, flip=True)


@when(parsers.parse("以 x={x:g}、y={y:g}、scale={scale:g} 建立精修合成請求"))
def build_request(
    ctx: dict[str, Any], x: float, y: float, scale: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_network(*_: Any, **__: Any) -> None:
        raise AssertionError("建立精修合成請求時不可連網")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    result = composite(ctx["photo"], ctx["cutout"], Placement(x, y, scale))
    ctx["pngs"] = (to_png(result.rough), to_png(result.mask))
    ctx["request"] = build_compose_request(
        rough_key=ROUGH_KEY, mask_key=MASK_KEY, identity_board_key=BOARD_KEY, keyframe_prompt=KEYFRAME_PROMPT
    )


# S11-01


@then(parsers.parse("粗合成圖尺寸為 {w:d}×{h:d}"))
@then(parsers.parse("粗合成圖尺寸仍為 {w:d}×{h:d}"))
def rough_size(ctx: dict[str, Any], w: int, h: int) -> None:
    assert ctx["result"].rough.size == (w, h)
    assert ctx["result"].rough.mode == "RGB"
    assert ctx["result"].mask.size == (w, h)


@then(parsers.parse("角色高度為 {h:d} 像素"))
def char_height(ctx: dict[str, Any], h: int) -> None:
    _, top, _, bottom = mask_bbox(ctx["result"].mask)
    assert abs((bottom - top) - h) <= 1


@then(parsers.parse("角色腳底中心位於 ({x:d}, {y:d})"))
def feet(ctx: dict[str, Any], x: int, y: int) -> None:
    cx, bottom = feet_center(ctx["result"].mask)
    assert abs(cx - x) <= 1
    assert abs(bottom - y) <= 1


# S11-02


@then("遮罩在角色不透明處為白色")
def mask_white(ctx: dict[str, Any]) -> None:
    mask = ctx["result"].mask
    assert mask.mode == "L"
    left, top, right, bottom = mask_bbox(mask)
    for px in [((left + right) // 2, (top + bottom) // 2), (left + 20, top + 20), (right - 20, bottom - 20)]:
        assert mask.getpixel(px) == 255


@then("遮罩在其他位置為黑色")
def mask_black(ctx: dict[str, Any]) -> None:
    mask = ctx["result"].mask
    left, top, right, bottom = mask_bbox(mask)
    outside = mask.copy()
    outside.paste(0, (left, top, right, bottom))
    assert outside.getbbox() is None
    assert mask.getpixel((0, 0)) == 0
    assert mask.getpixel((999, 1499)) == 0


# S11-03


@then("角色影像左右翻轉")
def flipped(ctx: dict[str, Any]) -> None:
    normal, mirrored = ctx["unflipped"], ctx["result"]
    assert feet_center(normal.mask) == feet_center(mirrored.mask)
    box = mask_bbox(normal.mask)
    diff = ImageChops.difference(ImageOps.mirror(normal.rough.crop(box)), mirrored.rough.crop(box))
    extrema = cast(tuple[tuple[int, int], ...], diff.getextrema())
    assert max(hi for _, hi in extrema) <= 2
    left, top, right, bottom = box
    probe = (left + 30, (top + bottom) // 2)
    r, _, b = cast(tuple[int, int, int], normal.rough.getpixel(probe))
    assert r > b  # 原圖左半是紅色
    r, _, b = cast(tuple[int, int, int], mirrored.rough.getpixel(probe))
    assert b > r  # 翻轉後左半是藍色


# S11-04


@then("合成成功")
def success(ctx: dict[str, Any]) -> None:
    assert "error" not in ctx
    _, _, right, _ = mask_bbox(ctx["result"].mask)
    assert right == 1000  # 角色右側被裁切


# S11-05


@then("應拋出擺放參數錯誤")
def placement_error(ctx: dict[str, Any]) -> None:
    assert isinstance(ctx.get("error"), PlacementError)
    assert "result" not in ctx
    assert "x" in str(ctx["error"])


# S11-06


@then("請求包含粗合成圖、角色遮罩與身份板參考圖")
def request_parts(ctx: dict[str, Any]) -> None:
    rough_png, mask_png = ctx["pngs"]
    assert rough_png.startswith(b"\x89PNG") and mask_png.startswith(b"\x89PNG")
    data = ctx["request"].to_input()
    assert data["base_image_key"] == ROUGH_KEY
    assert data["mask_key"] == MASK_KEY
    assert data["reference_keys"] == [BOARD_KEY]


@then("提示詞要求保留背景並統一光線與陰影")
def request_prompt(ctx: dict[str, Any]) -> None:
    prompt = ctx["request"].prompt
    assert "keep the background exactly unchanged" in prompt.lower()
    assert "match the lighting and shadows" in prompt.lower()
    assert KEYFRAME_PROMPT in prompt
