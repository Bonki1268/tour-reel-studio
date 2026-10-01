"""片尾卡：由品牌檔案產生 Logo、店名、地址與訂位 QR code（架構書 §5.6；spec 0014）。"""

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.domain.ports import BrandProfile, Project, Storage

WIDTH, HEIGHT = 1080, 1920
SAFE_TOP, SAFE_BOTTOM, SAFE_SIDE = 250, 400, 80
LOGO_BOX = (240, 300, 840, 700)  # 等比縮放到 ≤ 600×400，置中
OUTRO_SECONDS = 3


@dataclass(frozen=True)
class OutroInfo:
    name: str
    address: str = ""
    primary_color: str = "#C8553D"
    booking_url: str | None = None
    logo: bytes | None = None


@dataclass
class OutroCard:
    image: Image.Image
    layers: list[str] = field(default_factory=list)
    boxes: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    font_sizes: dict[str, int] = field(default_factory=dict)
    line_counts: dict[str, int] = field(default_factory=dict)


def parse_color(text: str) -> tuple[int, int, int]:
    raise NotImplementedError


def text_color(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    raise NotImplementedError


def fit_text(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, size: int, min_size: int, max_lines: int = 2
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    raise NotImplementedError


def make_card(info: OutroInfo) -> OutroCard:
    raise NotImplementedError


async def outro_info(project: Project, brand: BrandProfile, storage: Storage) -> OutroInfo:
    raise NotImplementedError


def card_to_clip_command(png: Path, mp4: Path, seconds: float = OUTRO_SECONDS, fps: int = 30) -> list[str]:
    raise NotImplementedError
