"""物件儲存路徑（架構書 §7；spec 0009）。其他模組不可自行拼接路徑。"""


def _seg(value: str) -> str:
    """路徑片段：非空、不含路徑分隔符號，且不是 . 或 ..。"""
    if not isinstance(value, str) or not value or value in (".", "..") or "/" in value or "\\" in value:
        raise ValueError(f"不合法的路徑片段：{value!r}")
    return value


def _num(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"版本、鏡頭與次數必須是 ≥ 1 的整數：{value!r}")
    return value


def _character(project_id: str, char_id: str, version: int) -> str:
    return f"projects/{_seg(project_id)}/characters/{_seg(char_id)}/v{_num(version)}"


def _take(video_id: str, shot_no: int, take: int) -> str:
    return f"videos/{_seg(video_id)}/shots/{_num(shot_no)}/take{_num(take)}"


def brand_logo(project_id: str) -> str:
    return f"projects/{_seg(project_id)}/brand/logo.png"


def identity_board(project_id: str, char_id: str, version: int) -> str:
    return f"{_character(project_id, char_id, version)}/identity_board.png"


def cutout(project_id: str, char_id: str, version: int) -> str:
    return f"{_character(project_id, char_id, version)}/cutout.png"


def scene_photo(project_id: str, photo_id: str) -> str:
    return f"projects/{_seg(project_id)}/scenes/{_seg(photo_id)}.jpg"


def rough(video_id: str, shot_no: int, take: int) -> str:
    return f"{_take(video_id, shot_no, take)}/rough.png"


def mask(video_id: str, shot_no: int, take: int) -> str:
    return f"{_take(video_id, shot_no, take)}/mask.png"


def keyframe(video_id: str, shot_no: int, take: int) -> str:
    return f"{_take(video_id, shot_no, take)}/keyframe.png"


def clip(video_id: str, shot_no: int, take: int) -> str:
    return f"{_take(video_id, shot_no, take)}/clip.mp4"


def render(video_id: str, render_id: str) -> str:
    return f"videos/{_seg(video_id)}/renders/{_seg(render_id)}.mp4"


def render_thumb(video_id: str, render_id: str) -> str:
    return f"videos/{_seg(video_id)}/renders/{_seg(render_id)}.jpg"
