"""B1 照片合成（spec 0011）。"""

import io

import pytest
from PIL import Image, ImageChops

from app.providers.base import ProviderRequest
from app.providers.composite import (
    ComposeRequest,
    Placement,
    PlacementError,
    build_compose_request,
    composite,
    to_png,
)
from tests.composite_support import BBOX, PHOTO_COLOR, make_cutout, make_photo, mask_bbox, transparent_cutout

pytestmark = pytest.mark.S11

CENTER = Placement(0.5, 0.9, 0.5)


# R-001


def test_r001_scale_keeps_aspect_ratio() -> None:
    result = composite(make_photo(), make_cutout(), CENTER)
    left, top, right, bottom = mask_bbox(result.mask)
    src_w, src_h = BBOX[2] - BBOX[0], BBOX[3] - BBOX[1]
    assert bottom - top == 750
    assert abs((right - left) - src_w * 750 / src_h) <= 1
    assert result.box == (left, top, right - left, bottom - top)


def test_r001_pixels_outside_character_unchanged() -> None:
    photo = make_photo()
    result = composite(photo, make_cutout(), CENTER)
    changed = ImageChops.difference(result.rough, photo).getbbox()
    assert changed is not None
    left, top, right, bottom = mask_bbox(result.mask)
    assert left <= changed[0] and top <= changed[1] and changed[2] <= right and changed[3] <= bottom
    assert result.rough.getpixel((10, 10)) == PHOTO_COLOR


def test_r001_same_ratios_across_resolutions() -> None:
    small = composite(make_photo((1000, 1500)), make_cutout(), CENTER)
    large = composite(make_photo((2000, 3000)), make_cutout(), CENTER)
    assert large.rough.size == (2000, 3000)
    for a, b in zip(mask_bbox(small.mask), mask_bbox(large.mask), strict=True):
        assert abs(a * 2 - b) <= 2


def test_r001_exif_orientation_applied() -> None:
    raw = Image.new("RGB", (1500, 1000), PHOTO_COLOR)
    exif = Image.Exif()
    exif[0x0112] = 6  # 需順時針轉 90 度
    buf = io.BytesIO()
    raw.save(buf, "JPEG", exif=exif)
    photo = Image.open(io.BytesIO(buf.getvalue()))
    result = composite(photo, make_cutout(), CENTER)
    assert result.rough.size == (1000, 1500)
    assert mask_bbox(result.mask)[3] == 1350


def test_r001_accepts_palette_and_rgb_photo_modes() -> None:
    result = composite(make_photo().convert("P"), make_cutout(), CENTER)
    assert result.rough.mode == "RGB"


# R-002


def test_r002_mask_matches_alpha() -> None:
    cutout = make_cutout()
    result = composite(make_photo(), cutout, CENTER)
    left, top, w, h = result.box
    expected_alpha = cutout.getchannel("A").crop(BBOX).resize((w, h), Image.Resampling.LANCZOS)
    expected = Image.new("L", result.mask.size, 0)
    expected.paste(expected_alpha, (left, top))
    assert ImageChops.difference(result.mask, expected).getbbox() is None
    values = set(result.mask.getdata())
    assert 0 in values and 255 in values
    assert any(0 < v < 255 for v in values)  # 半透明邊緣保留


# R-004


def test_r004_partial_outside_is_cropped() -> None:
    result = composite(make_photo(), make_cutout(), Placement(0.05, 0.3, 0.5))
    left, top, right, bottom = mask_bbox(result.mask)
    assert left == 0 and top == 0
    assert result.rough.size == (1000, 1500)
    assert result.box[0] < 0 and result.box[1] < 0


@pytest.mark.parametrize("placement", [Placement(0.5, 0.0, 0.5), Placement(0.5, 0.0, 1.0)])
def test_r004_fully_outside_raises(placement: Placement) -> None:
    with pytest.raises(PlacementError, match="畫面外"):
        composite(make_photo(), make_cutout(), placement)


def test_r004_transparent_cutout_raises() -> None:
    with pytest.raises(PlacementError, match="不透明"):
        composite(make_photo(), transparent_cutout(), CENTER)


# R-005


@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"x": 1.2}, "x"),
        ({"x": -0.1}, "x"),
        ({"y": -0.01}, "y"),
        ({"y": 1.5}, "y"),
        ({"scale": 0}, "scale"),
        ({"scale": -1}, "scale"),
        ({"scale": 1.2}, "scale"),
        ({"x": float("nan")}, "x"),
    ],
)
def test_r005_out_of_range_names_parameter(kwargs: dict[str, float], name: str) -> None:
    data: dict[str, float] = {"x": 0.5, "y": 0.9, "scale": 0.5, **kwargs}
    with pytest.raises(PlacementError, match=name):
        Placement(data["x"], data["y"], data["scale"])
    with pytest.raises(PlacementError, match=name):
        Placement.from_mapping(data)


def test_r005_lists_every_bad_parameter() -> None:
    with pytest.raises(PlacementError) as exc:
        Placement(1.2, -1, 0)
    message = str(exc.value)
    assert "x" in message and "y" in message and "scale" in message


def test_r005_boundaries_accepted() -> None:
    assert Placement(0, 0, 1) == Placement(0.0, 0.0, 1.0)
    assert Placement(1, 1, 0.01, True).flip is True


def test_r005_from_mapping_reads_plan_placement() -> None:
    p = Placement.from_mapping({"x": 0.3, "y": 0.8, "scale": 0.4, "flip": True})
    assert p == Placement(0.3, 0.8, 0.4, True)
    assert Placement.from_mapping({"x": 0.3, "y": 0.8, "scale": 0.4}).flip is False


@pytest.mark.parametrize("data", [{"y": 0.8, "scale": 0.4}, {"x": "left", "y": 0.8, "scale": 0.4}])
def test_r005_from_mapping_rejects_missing_or_non_numeric(data: dict[str, object]) -> None:
    with pytest.raises(PlacementError, match="x"):
        Placement.from_mapping(data)


# R-006


def test_r006_prompt_template_keeps_background_and_lighting() -> None:
    req = build_compose_request(
        rough_key="r.png", mask_key="m.png", identity_board_key="b.png", keyframe_prompt="Guide at the temple gate"
    )
    prompt = req.prompt.lower()
    assert "keep the background exactly unchanged" in prompt
    assert "match the lighting and shadows" in prompt
    assert "no text" in prompt
    assert req.prompt.rstrip().endswith("Guide at the temple gate")


def test_r006_to_input_shape() -> None:
    req = build_compose_request(
        rough_key="r.png", mask_key="m.png", identity_board_key="b.png", keyframe_prompt="Shot one"
    )
    assert req == ComposeRequest("r.png", "m.png", ("b.png",), req.prompt)
    data = req.to_input()
    assert data == {"base_image_key": "r.png", "mask_key": "m.png", "reference_keys": ["b.png"], "prompt": req.prompt}
    provider_req = ProviderRequest(model="m", input=data, provider_idempotency_key="k")
    assert provider_req.input["prompt"] == req.prompt


def test_r006_to_png_roundtrip() -> None:
    result = composite(make_photo(), make_cutout(), CENTER)
    data = to_png(result.mask)
    back = Image.open(io.BytesIO(data))
    assert back.format == "PNG" and back.size == (1000, 1500)
    assert ImageChops.difference(back.convert("L"), result.mask).getbbox() is None
