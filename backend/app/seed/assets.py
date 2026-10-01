"""種子素材前處理（spec 0017 R-003、R-006）。"""

import hashlib
import io

from PIL import Image, ImageOps, UnidentifiedImageError

SCENE_SIZE = (1080, 1920)
SCENE_QUALITY = 88


def content_id(data: bytes) -> str:
    """以檔案內容決定的識別碼（sha256 前 16 碼）：內容相同即視為同一份素材。"""
    return hashlib.sha256(data).hexdigest()[:16]


def prepare_scene(data: bytes) -> bytes:
    """實景照：依 EXIF 轉正、置中裁成 9:16、縮成 1080×1920 JPEG。"""
    with Image.open(io.BytesIO(data)) as image:
        upright = ImageOps.exif_transpose(image).convert("RGB")
    fitted = ImageOps.fit(upright, SCENE_SIZE, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    buf = io.BytesIO()
    fitted.save(buf, "JPEG", quality=SCENE_QUALITY)
    return buf.getvalue()


def prepare_cutout(data: bytes) -> bytes:
    """去背圖：轉為 RGBA PNG，裁掉不透明範圍下方的透明邊（保留上、左、右透明邊）。"""
    with Image.open(io.BytesIO(data)) as image:
        rgba = image.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox is not None:
        rgba = rgba.crop((0, 0, rgba.width, bbox[3]))
    buf = io.BytesIO()
    rgba.save(buf, "PNG")
    return buf.getvalue()


def has_transparent_background(data: bytes) -> bool:
    """含 alpha 通道且四個角落完全透明。"""
    try:
        with Image.open(io.BytesIO(data)) as image:
            if "A" not in image.getbands() and "transparency" not in image.info:
                return False
            alpha = image.convert("RGBA").getchannel("A")
    except (UnidentifiedImageError, OSError):
        return False
    w, h = alpha.size
    return all(alpha.getpixel(p) == 0 for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)))
