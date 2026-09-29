"""B1 粗合成：把角色去背圖依擺放參數疊到實景照上（架構書 §5.3、開發計畫 S11 的定義）。

擺放參數（皆為 0–1 比例，與解析度無關）：
- x、y：角色腳底中心在畫面中的位置（x 由左至右、y 由上至下）
- scale：角色高度 ÷ 畫面高度
- flip：水平翻轉

Seedance 2.5 image-to-video 沒有 aspect_ratio 參數，輸出構圖跟隨首幀，
所以先把實景照置中裁成 9:16（720×1280），擺放座標以裁切後的畫面為準。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

FRAME_W, FRAME_H = 720, 1280  # 9:16、Seedance 720p


@dataclass(frozen=True)
class Placement:
    x: float
    y: float
    scale: float
    flip: bool = False


def crop_to_frame(photo: Image.Image) -> Image.Image:
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    return ImageOps.fit(photo, (FRAME_W, FRAME_H), method=Image.Resampling.LANCZOS)


def composite(photo_path: Path, cutout_path: Path, p: Placement) -> tuple[Image.Image, Image.Image]:
    """回傳 (粗合成圖 RGB, 角色遮罩 L)。角色完全在畫面外時拋出 ValueError。"""
    frame = crop_to_frame(Image.open(photo_path))
    char = Image.open(cutout_path).convert("RGBA")
    bbox = char.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("角色圖沒有不透明像素，請確認是去背 PNG")
    char = char.crop(bbox)  # 去掉透明邊，讓腳底貼齊圖片底部
    if p.flip:
        char = ImageOps.mirror(char)

    h = max(1, round(p.scale * FRAME_H))
    w = max(1, round(char.width * h / char.height))  # 保持長寬比
    char = char.resize((w, h), Image.Resampling.LANCZOS)
    left = round(p.x * FRAME_W - w / 2)
    top = round(p.y * FRAME_H - h)
    if left >= FRAME_W or top >= FRAME_H or left + w <= 0 or top + h <= 0:
        raise ValueError(f"角色完全在畫面外：{p}")

    rough = frame.copy()
    rough.paste(char, (left, top), char)  # 超出部分由 paste 自動裁切
    mask = Image.new("L", (FRAME_W, FRAME_H), 0)
    mask.paste(char.getchannel("A"), (left, top))
    return rough, mask
