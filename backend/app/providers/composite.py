"""B1 照片合成：依擺放參數產生粗合成圖與角色遮罩，並組出精修合成請求（架構書 §5.3；spec 0011）。

純運算：不連網、不寫入儲存。上傳圖片與轉成供應商欄位由 S12 的 adapter 處理。
"""

import io
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageOps

# 精修提示詞（英文，S00 結論：英文效果較好）
REFINE_PROMPT = (
    "Blend the character into the photo so it looks naturally photographed on location.\n"
    "Keep the background exactly unchanged: same buildings, landmarks, composition and framing.\n"
    "Keep the character's position, size and pose from the base image; match the identity reference.\n"
    "Match the lighting and shadows of the scene, add a natural contact shadow under the feet.\n"
    "Photorealistic, no text, no logos.\n"
    "Shot: {keyframe_prompt}"
)


class PlacementError(ValueError):
    """擺放參數超出範圍，或角色無法放進照片。"""


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or math.isnan(value):
        return None
    return float(value)


@dataclass(frozen=True)
class Placement:
    """x、y：角色腳底中心的比例位置（左上為 0,0）；scale：角色高度 ÷ 照片高度。"""

    x: float
    y: float
    scale: float
    flip: bool = False

    def __post_init__(self) -> None:
        bad = [
            f"{name}={value!r}（應介於 {desc}）"
            for name, value, low, low_inclusive, desc in (
                ("x", self.x, 0.0, True, "0 到 1"),
                ("y", self.y, 0.0, True, "0 到 1"),
                ("scale", self.scale, 0.0, False, "大於 0、不超過 1"),
            )
            if (n := _number(value)) is None or n > 1 or n < low or (n == low and not low_inclusive)
        ]
        if bad:
            raise PlacementError("擺放參數超出範圍：" + "、".join(bad))

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Placement":
        """接受 S10 企劃的 placement dict；缺少或非數值的欄位視為超出範圍。"""
        return cls(data.get("x"), data.get("y"), data.get("scale"), bool(data.get("flip", False)))  # type: ignore[arg-type]


@dataclass(frozen=True)
class CompositeResult:
    rough: Image.Image
    mask: Image.Image
    box: tuple[int, int, int, int]  # 角色在照片中的 left, top, width, height（可能部分超出）


def composite(photo: Image.Image, cutout: Image.Image, placement: Placement) -> CompositeResult:
    """回傳與實景照同尺寸的粗合成圖（RGB）與角色遮罩（L）；部分超出邊界的角色會被裁切。"""
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    char = cutout.convert("RGBA")
    bbox = char.getchannel("A").getbbox()
    if bbox is None:
        raise PlacementError("角色圖沒有不透明像素，請確認是去背 PNG")
    char = char.crop(bbox)  # 去掉透明邊，讓腳底貼齊圖片底部
    if placement.flip:
        char = ImageOps.mirror(char)

    pw, ph = photo.size
    h = max(1, round(placement.scale * ph))
    w = max(1, round(char.width * h / char.height))  # 保持長寬比
    char = char.resize((w, h), Image.Resampling.LANCZOS)
    left = round(placement.x * pw - w / 2)
    top = round(placement.y * ph - h)
    if left >= pw or top >= ph or left + w <= 0 or top + h <= 0:
        raise PlacementError(f"角色完全在畫面外：{placement}")

    rough = photo.copy()
    rough.paste(char, (left, top), char)  # 超出部分由 paste 自動裁切
    mask = Image.new("L", photo.size, 0)
    mask.paste(char.getchannel("A"), (left, top))
    return CompositeResult(rough=rough, mask=mask, box=(left, top, w, h))


def to_png(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


@dataclass(frozen=True)
class ComposeRequest:
    """精修合成請求：以儲存 key 引用圖片；to_input() 作為 S06 ProviderRequest.input。"""

    base_image_key: str
    mask_key: str
    reference_keys: tuple[str, ...]
    prompt: str

    def to_input(self) -> dict[str, Any]:
        return {
            "base_image_key": self.base_image_key,
            "mask_key": self.mask_key,
            "reference_keys": list(self.reference_keys),
            "prompt": self.prompt,
        }


def build_compose_request(
    *, rough_key: str, mask_key: str, identity_board_key: str, keyframe_prompt: str
) -> ComposeRequest:
    return ComposeRequest(
        base_image_key=rough_key,
        mask_key=mask_key,
        reference_keys=(identity_board_key,),
        prompt=REFINE_PROMPT.format(keyframe_prompt=keyframe_prompt.strip()),
    )
