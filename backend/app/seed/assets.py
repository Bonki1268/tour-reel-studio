"""種子素材前處理（spec 0017 R-003、R-006）。"""

SCENE_SIZE = (1080, 1920)


def content_id(data: bytes) -> str:
    raise NotImplementedError


def prepare_scene(data: bytes) -> bytes:
    raise NotImplementedError


def prepare_cutout(data: bytes) -> bytes:
    raise NotImplementedError


def has_transparent_background(data: bytes) -> bool:
    raise NotImplementedError
