"""S14 測試共用：程式產生的 Logo、片尾資訊與 QR 解碼。"""

import io

import cv2
import numpy as np
from PIL import Image

from app.render.outro import LOGO_BOX, OutroCard, OutroInfo

LOGO_BLUE = (0, 0, 255)


def make_logo(size: tuple[int, int] = (240, 160)) -> bytes:
    img = Image.new("RGBA", size, (*LOGO_BLUE, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def info(**overrides: object) -> OutroInfo:
    values: dict[str, object] = {
        "name": "梅子農場",
        "address": "台南市楠西區",
        "primary_color": "#C8553D",
        "booking_url": "https://example.com/book",
        "logo": None,
    }
    values.update(overrides)
    return OutroInfo(**values)  # type: ignore[arg-type]


def blue_pixels(card: OutroCard, box: tuple[int, int, int, int] = LOGO_BOX) -> int:
    region = card.image.convert("RGB").crop(box)
    return sum(1 for px in region.getdata() if px == LOGO_BLUE)


def decode_qr(card: OutroCard) -> str:
    arr = cv2.cvtColor(np.array(card.image.convert("RGB")), cv2.COLOR_RGB2BGR)
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(arr)
    return str(text)
