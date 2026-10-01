"""B1 合成測試用圖片（spec 0011）：全部以程式產生，不依賴外部檔案。"""

from PIL import Image

PHOTO_COLOR = (40, 120, 60)
RED = (220, 30, 30)
BLUE = (30, 30, 220)

# 角色去背圖 400×800：不透明區塊 cols 100–299、rows 50–749（左半紅、右半藍），外圍 2 像素半透明
OPAQUE = (100, 50, 300, 750)
RING = 2
BBOX = (OPAQUE[0] - RING, OPAQUE[1] - RING, OPAQUE[2] + RING, OPAQUE[3] + RING)


def make_photo(size: tuple[int, int] = (1000, 1500)) -> Image.Image:
    return Image.new("RGB", size, PHOTO_COLOR)


def make_cutout() -> Image.Image:
    img = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
    img.paste((128, 128, 128, 128), BBOX)
    left, top, right, bottom = OPAQUE
    mid = (left + right) // 2
    img.paste((*RED, 255), (left, top, mid, bottom))
    img.paste((*BLUE, 255), (mid, top, right, bottom))
    return img


def transparent_cutout() -> Image.Image:
    return Image.new("RGBA", (400, 800), (0, 0, 0, 0))


def mask_bbox(mask: Image.Image) -> tuple[int, int, int, int]:
    box = mask.getbbox()
    assert box is not None, "遮罩全黑"
    return box


def feet_center(mask: Image.Image) -> tuple[float, int]:
    left, _, right, bottom = mask_bbox(mask)
    return (left + right) / 2, bottom
