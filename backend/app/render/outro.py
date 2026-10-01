"""片尾卡：由品牌檔案產生 Logo、店名、地址與訂位 QR code（架構書 §5.6；spec 0014）。

版面（1080×1920）：內容只放在 IG Reels 安全區（上 250、下 400、左右 80 px 以內）。
Logo 區 y 300–700；店名、地址依序在下方；訂位 QR code 在地址下方。
"""

import io
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_M

from app.domain.ports import BrandProfile, Project, Storage
from app.render.timeline import DEFAULT_COLOR
from app.storage import keys
from app.storage.objects import ObjectNotFound

WIDTH, HEIGHT = 1080, 1920
SAFE_TOP, SAFE_BOTTOM, SAFE_SIDE = 250, 400, 80
LOGO_BOX = (240, 300, 840, 700)  # 等比縮放到 ≤ 600×400，置中
OUTRO_SECONDS = 3
FONT_PATH = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "NotoSansTC-Bold.otf"
TEXT_WIDTH = WIDTH - 2 * SAFE_SIDE
CONTENT_BOTTOM = HEIGHT - SAFE_BOTTOM
NAME_TOP = 760
QR_SIZE, QR_MIN = 400, 360
_COLOR = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})")

logger = logging.getLogger(__name__)

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class OutroInfo:
    name: str
    address: str = ""
    primary_color: str = DEFAULT_COLOR
    booking_url: str | None = None
    logo: bytes | None = None


@dataclass
class OutroCard:
    image: Image.Image
    layers: list[str] = field(default_factory=list)
    boxes: dict[str, Box] = field(default_factory=dict)
    font_sizes: dict[str, int] = field(default_factory=dict)
    line_counts: dict[str, int] = field(default_factory=dict)


def parse_color(text: str) -> tuple[int, int, int]:
    """#RGB 或 #RRGGBB（不分大小寫）→ (r, g, b)。"""
    match = _COLOR.fullmatch(text) if isinstance(text, str) else None
    if match is None:
        raise ValueError(f"無法解析的顏色：{text!r}（應為 #RGB 或 #RRGGBB）")
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    r, g, b = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    return r, g, b


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def text_color(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """WCAG 相對亮度 > 0.5 用黑字，否則白字。"""
    return (0, 0, 0) if _luminance(rgb) > 0.5 else (255, 255, 255)


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """逐字換行（適用中文；英文單字也可能在字中斷開）。"""
    lines, line = [], ""
    for ch in text:
        if line and draw.textlength(line + ch, font=font) > max_width:
            lines.append(line)
            line = ch.lstrip()
        else:
            line += ch
    return [*lines, line] if line else lines


def fit_text(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, size: int, min_size: int, max_lines: int = 2
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """先縮小字級求單行；仍放不下時換行（最多 max_lines 行）；最小字級仍放不下時截斷加「…」。"""
    sizes = range(size, min_size - 1, -2)
    for s in sizes:
        font = _font(s)
        if draw.textlength(text, font=font) <= max_width:
            return font, [text]
    for s in sizes:
        font = _font(s)
        lines = _wrap(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
    font = _font(min_size)
    lines = _wrap(draw, text, font, max_width)[:max_lines]
    while lines[-1] and draw.textlength(lines[-1] + "…", font=font) > max_width:
        lines[-1] = lines[-1][:-1]
    lines[-1] += "…"
    return font, lines


def _decode_logo(data: bytes | None) -> Image.Image | None:
    if not data:
        return None
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception:  # 不是圖片或檔案損壞：視為沒有 Logo
        logger.warning("Logo 無法解碼，以店名文字代替")
        return None
    return image.convert("RGBA")


def _union(boxes: list[Box]) -> Box:
    lefts, tops, rights, bottoms = zip(*boxes, strict=True)
    return min(lefts), min(tops), max(rights), max(bottoms)


class _Painter:
    def __init__(self, card: OutroCard, color: tuple[int, int, int]) -> None:
        self.card = card
        self.draw = ImageDraw.Draw(card.image)
        self.color = color

    def text(
        self, layer: str, text: str, top: int, size: int, min_size: int, center_in: Box | None = None
    ) -> int:
        """置中繪製文字，回傳下緣 y；center_in 指定時在該區塊內垂直置中。"""
        font, lines = fit_text(self.draw, text, TEXT_WIDTH, size, min_size)
        step = math.ceil(font.size * 1.25)
        if center_in is not None:
            top = center_in[1] + (center_in[3] - center_in[1] - step * len(lines)) // 2
        boxes = []
        for n, line in enumerate(lines):
            xy = (WIDTH // 2, top + n * step)
            self.draw.text(xy, line, font=font, fill=self.color, anchor="ma")
            left, top_, right, bottom = self.draw.textbbox(xy, line, font=font, anchor="ma")
            boxes.append((int(left), int(top_), int(right), int(bottom)))
        self.card.layers.append(layer)
        self.card.boxes[layer] = _union(boxes)
        self.card.font_sizes[layer] = int(font.size)
        self.card.line_counts[layer] = len(lines)
        return top + step * len(lines)


def _qr_image(url: str) -> Image.Image:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=1, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    modules = qr.modules_count + 2 * qr.border
    qr.box_size = max(QR_SIZE // modules, math.ceil(QR_MIN / modules))
    image: Any = qr.make_image(fill_color="black", back_color="white")
    return image.get_image().convert("RGB")  # type: ignore[no-any-return]


def make_card(info: OutroInfo) -> OutroCard:
    """依品牌資訊繪製 1080×1920 片尾卡（純運算）。"""
    background = parse_color(info.primary_color)
    card = OutroCard(Image.new("RGB", (WIDTH, HEIGHT), background), ["background"])
    card.boxes["background"] = (0, 0, WIDTH, HEIGHT)
    painter = _Painter(card, text_color(background))

    logo = _decode_logo(info.logo)
    if logo is not None:
        box_w, box_h = LOGO_BOX[2] - LOGO_BOX[0], LOGO_BOX[3] - LOGO_BOX[1]
        ratio = min(box_w / logo.width, box_h / logo.height)
        logo = logo.resize((max(1, round(logo.width * ratio)), max(1, round(logo.height * ratio))),
                           Image.Resampling.LANCZOS)
        left = (WIDTH - logo.width) // 2
        top = LOGO_BOX[1] + (box_h - logo.height) // 2
        card.image.paste(logo, (left, top), logo)
        card.layers.append("logo")
        card.boxes["logo"] = (left, top, left + logo.width, top + logo.height)
        bottom = painter.text("name", info.name, NAME_TOP, 96, 48)
    else:  # 沒有 Logo：放大的店名佔用 Logo 位置
        painter.text("name", info.name, LOGO_BOX[1], 120, 72, center_in=LOGO_BOX)
        bottom = NAME_TOP - 40

    if info.address.strip():
        bottom = painter.text("address", info.address.strip(), bottom + 40, 48, 32)

    if info.booking_url:
        qr = _qr_image(info.booking_url)
        top = min(max(bottom + 60, 1000), CONTENT_BOTTOM - qr.height)
        left = (WIDTH - qr.width) // 2
        card.image.paste(qr, (left, top))
        card.layers.append("qr")
        card.boxes["qr"] = (left, top, left + qr.width, top + qr.height)
    return card


async def _read(storage: Storage, key: str | None) -> bytes | None:
    if not key:
        return None
    try:
        return await storage.get(key)
    except ObjectNotFound:
        return None


async def outro_info(project: Project, brand: BrandProfile, storage: Storage) -> OutroInfo:
    """由品牌檔案組出片尾資訊：主色取第一個顏色（格式錯誤用預設）、訂位網址取 info.booking_url 或 website。"""
    colors = brand.visual.get("colors")
    color = DEFAULT_COLOR
    if isinstance(colors, list) and colors and isinstance(colors[0], str):
        try:
            parse_color(colors[0])
            color = colors[0]
        except ValueError:
            logger.warning("品牌主色格式錯誤，使用預設主色")
    booking = brand.info.get("booking_url") or brand.info.get("website")
    logo_meta = brand.visual.get("logo")
    logo_key = logo_meta.get("key") if isinstance(logo_meta, dict) else None
    logo = await _read(storage, str(logo_key) if logo_key else None) or await _read(
        storage, keys.brand_logo(project.id)
    )
    return OutroInfo(
        name=project.name,
        address=str(brand.info.get("address") or ""),
        primary_color=color,
        booking_url=str(booking) if booking else None,
        logo=logo,
    )


def card_to_clip_command(png: Path, mp4: Path, seconds: float = OUTRO_SECONDS, fps: int = 30) -> list[str]:
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-i", str(png),
        "-t", f"{seconds:g}", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4),
    ]
