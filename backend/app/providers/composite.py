"""B1 照片合成：依擺放參數產生粗合成圖與角色遮罩，並組出精修合成請求（架構書 §5.3；spec 0011）。"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from PIL import Image


class PlacementError(ValueError):
    """擺放參數超出範圍，或角色無法放進照片。"""


@dataclass(frozen=True)
class Placement:
    """x、y：角色腳底中心的比例位置（左上為 0,0）；scale：角色高度 ÷ 照片高度。"""

    x: float
    y: float
    scale: float
    flip: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Placement":
        raise NotImplementedError


@dataclass(frozen=True)
class CompositeResult:
    rough: Image.Image
    mask: Image.Image
    box: tuple[int, int, int, int]  # 角色在照片中的 left, top, width, height（可能部分超出）


def composite(photo: Image.Image, cutout: Image.Image, placement: Placement) -> CompositeResult:
    raise NotImplementedError


def to_png(image: Image.Image) -> bytes:
    raise NotImplementedError


@dataclass(frozen=True)
class ComposeRequest:
    base_image_key: str
    mask_key: str
    reference_keys: tuple[str, ...]
    prompt: str

    def to_input(self) -> dict[str, Any]:
        raise NotImplementedError


def build_compose_request(
    *, rough_key: str, mask_key: str, identity_board_key: str, keyframe_prompt: str
) -> ComposeRequest:
    raise NotImplementedError
