"""片尾卡（spec 0014）。"""

from pathlib import Path

import pytest
from PIL import Image

from app.domain.ports import BrandProfile, Project
from app.render.outro import (
    HEIGHT,
    LOGO_BOX,
    SAFE_BOTTOM,
    SAFE_SIDE,
    SAFE_TOP,
    WIDTH,
    card_to_clip_command,
    make_card,
    outro_info,
    parse_color,
    text_color,
)
from app.storage import keys
from app.storage.objects import MemoryStorage
from tests.outro_support import blue_pixels, decode_qr, info, make_logo

pytestmark = pytest.mark.S14


# R-001


@pytest.mark.parametrize("logo", [None, make_logo()])
def test_r001_safe_area_for_all_layers(logo: bytes | None) -> None:
    card = make_card(info(logo=logo))
    assert card.layers[0] == "background"
    for name, (left, top, right, bottom) in card.boxes.items():
        if name == "background":
            continue
        assert left >= SAFE_SIDE and right <= WIDTH - SAFE_SIDE, name
        assert top >= SAFE_TOP and bottom <= HEIGHT - SAFE_BOTTOM, name


def test_r001_logo_scaled_within_box() -> None:
    card = make_card(info(logo=make_logo((2000, 500))))  # 很寬的 Logo
    left, top, right, bottom = card.boxes["logo"]
    assert right - left <= 600 and bottom - top <= 400
    assert (right - left) / (bottom - top) == pytest.approx(4, rel=0.02)
    assert LOGO_BOX[0] <= left and right <= LOGO_BOX[2] and LOGO_BOX[1] <= top and bottom <= LOGO_BOX[3]
    assert (left + right) // 2 == pytest.approx(WIDTH // 2, abs=1)


def test_r001_layer_order() -> None:
    card = make_card(info(logo=make_logo()))
    assert card.layers == ["background", "logo", "name", "address", "qr"]


# R-002


def test_r002_no_booking_url_skips_qr() -> None:
    card = make_card(info(booking_url=None))
    assert "qr" not in card.layers
    assert decode_qr(card) == ""


def test_r002_qr_min_size_and_white_background() -> None:
    card = make_card(info(booking_url="https://example.com/" + "x" * 120))
    left, top, right, bottom = card.boxes["qr"]
    assert right - left >= 360 and bottom - top >= 360
    assert card.image.convert("RGB").getpixel((left + 2, top + 2)) == (255, 255, 255)
    assert decode_qr(card) == "https://example.com/" + "x" * 120


# R-003


@pytest.mark.parametrize("logo", [b"", b"not an image"])
def test_r003_broken_logo_treated_as_missing(logo: bytes) -> None:
    card = make_card(info(logo=logo))
    assert "logo" not in card.layers and "name" in card.layers
    assert blue_pixels(card) == 0
    assert card.boxes["name"][1] < LOGO_BOX[3]  # 店名佔用 Logo 位置


async def test_r003_outro_info_reads_brand_profile() -> None:
    storage = MemoryStorage()
    await storage.put("projects/p1/brand/logo.png", make_logo(), "image/png")
    project = Project(id="p1", name="梅子農場")
    brand = BrandProfile(
        project_id="p1",
        visual={"colors": ["#6B8E23"], "logo": {"key": "projects/p1/brand/logo.png"}},
        info={"address": "南投縣信義鄉", "booking_url": "https://example.com/book", "website": "https://x"},
    )
    result = await outro_info(project, brand, storage)
    assert (result.name, result.address, result.primary_color) == ("梅子農場", "南投縣信義鄉", "#6B8E23")
    assert result.booking_url == "https://example.com/book"
    assert result.logo == make_logo()


async def test_r003_outro_info_fallbacks() -> None:
    storage = MemoryStorage()
    project = Project(id="p2", name="店")
    brand = BrandProfile(
        project_id="p2", visual={"logo": {"key": "missing.png"}}, info={"website": "https://w"}
    )
    result = await outro_info(project, brand, storage)
    assert result.logo is None and result.booking_url == "https://w" and result.address == ""
    assert result.primary_color == "#C8553D"
    await storage.put(keys.brand_logo("p2"), make_logo(), "image/png")
    assert (await outro_info(project, brand, storage)).logo == make_logo()


async def test_r003_outro_info_invalid_color_uses_default() -> None:
    brand = BrandProfile(project_id="p3", visual={"colors": ["not-a-color"]})
    result = await outro_info(Project(id="p3", name="店"), brand, MemoryStorage())
    assert result.primary_color == "#C8553D"


# R-004


@pytest.mark.parametrize(
    ("text", "rgb"),
    [
        ("#C8553D", (200, 85, 61)),
        ("#c8553d", (200, 85, 61)),
        ("#C53", (204, 85, 51)),
        ("#fff", (255, 255, 255)),
    ],
)
def test_r004_parse_color(text: str, rgb: tuple[int, int, int]) -> None:
    assert parse_color(text) == rgb


@pytest.mark.parametrize("text", ["C8553D", "#C8553", "#GG0000", "", "#C8553DFF"])
def test_r004_parse_color_rejects(text: str) -> None:
    with pytest.raises(ValueError) as exc:
        parse_color(text)
    assert repr(text) in str(exc.value)


@pytest.mark.parametrize(
    ("color", "expected"),
    [
        ("#F5DEB3", (0, 0, 0)),
        ("#FFFFFF", (0, 0, 0)),
        ("#6B8E23", (255, 255, 255)),
        ("#C8553D", (255, 255, 255)),
        ("#000000", (255, 255, 255)),
    ],
)
def test_r004_text_color_by_luminance(color: str, expected: tuple[int, int, int]) -> None:
    assert text_color(parse_color(color)) == expected


def test_r004_card_uses_text_color() -> None:
    card = make_card(info(primary_color="#F5DEB3", booking_url=None))
    left, top, right, bottom = card.boxes["name"]
    region = card.image.convert("RGB").crop((left, top, right, bottom))
    assert (0, 0, 0) in set(region.getdata())


# R-005


def test_r005_long_name_shrinks_within_safe_area() -> None:
    normal = make_card(info(logo=make_logo()))
    long = make_card(info(logo=make_logo(), name="梅" * 30))
    n_left, n_top, n_right, n_bottom = normal.boxes["name"]
    left, top, right, bottom = long.boxes["name"]
    assert left >= SAFE_SIDE and right <= WIDTH - SAFE_SIDE
    assert long.font_sizes["name"] < normal.font_sizes["name"]
    assert long.font_sizes["name"] >= 48


def test_r005_long_address_wraps() -> None:
    card = make_card(info(address="台南市楠西區" * 8))
    left, top, right, bottom = card.boxes["address"]
    assert left >= SAFE_SIDE and right <= WIDTH - SAFE_SIDE
    assert card.line_counts["address"] == 2
    assert card.font_sizes["address"] >= 32


# R-006


def test_r006_card_to_clip_command() -> None:
    cmd = card_to_clip_command(Path("/tmp/c.png"), Path("/tmp/c.mp4"))
    assert cmd[0] == "ffmpeg"
    assert cmd[cmd.index("-loop") + 1] == "1"
    assert cmd[cmd.index("-t") + 1] == "3"
    assert cmd[cmd.index("-r") + 1] == "30"
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[-1] == "/tmp/c.mp4"


def test_r006_card_is_rgb_image() -> None:
    image = make_card(info()).image
    assert isinstance(image, Image.Image) and image.mode == "RGB"
