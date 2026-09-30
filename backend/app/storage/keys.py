"""物件儲存路徑（架構書 §7；spec 0009）。其他模組不可自行拼接路徑。"""


def brand_logo(project_id: str) -> str:
    raise NotImplementedError


def identity_board(project_id: str, char_id: str, version: int) -> str:
    raise NotImplementedError


def cutout(project_id: str, char_id: str, version: int) -> str:
    raise NotImplementedError


def scene_photo(project_id: str, photo_id: str) -> str:
    raise NotImplementedError


def rough(video_id: str, shot_no: int, take: int) -> str:
    raise NotImplementedError


def keyframe(video_id: str, shot_no: int, take: int) -> str:
    raise NotImplementedError


def clip(video_id: str, shot_no: int, take: int) -> str:
    raise NotImplementedError


def render(video_id: str, render_id: str) -> str:
    raise NotImplementedError
