"""物件儲存路徑（spec 0009 R-003）。"""

import re
from pathlib import Path

import pytest

from app.storage import keys

pytestmark = pytest.mark.S09

APP_DIR = Path(__file__).resolve().parents[2] / "app"


def test_r003_all_paths_match_section7() -> None:
    assert keys.brand_logo("p1") == "projects/p1/brand/logo.png"
    assert keys.identity_board("p1", "c1", 2) == "projects/p1/characters/c1/v2/identity_board.png"
    assert keys.cutout("p1", "c1", 2) == "projects/p1/characters/c1/v2/cutout.png"
    assert keys.scene_photo("p1", "ph_01") == "projects/p1/scenes/ph_01.jpg"
    assert keys.rough("v1", 1, 2) == "videos/v1/shots/1/take2/rough.png"
    assert keys.keyframe("v1", 1, 2) == "videos/v1/shots/1/take2/keyframe.png"
    assert keys.clip("v1", 3, 1) == "videos/v1/shots/3/take1/clip.mp4"
    assert keys.render("v1", "r9") == "videos/v1/renders/r9.mp4"


@pytest.mark.parametrize("bad", ["", "a/b", "..", ".", "a\\b", "../p1"])
def test_r003_rejects_invalid_segments(bad: str) -> None:
    with pytest.raises(ValueError):
        keys.scene_photo(bad, "ph_01")
    with pytest.raises(ValueError):
        keys.render("v1", bad)
    with pytest.raises(ValueError):
        keys.keyframe(bad, 1, 1)


@pytest.mark.parametrize("bad", [0, -1, True])
def test_r003_rejects_invalid_numbers(bad: int) -> None:
    with pytest.raises(ValueError):
        keys.keyframe("v1", bad, 1)
    with pytest.raises(ValueError):
        keys.clip("v1", 1, bad)
    with pytest.raises(ValueError):
        keys.cutout("p1", "c1", bad)


def test_r003_no_hardcoded_paths_in_app() -> None:
    """路徑只能由 keys.py 產生：其他模組不可出現以 videos/ 或 projects/ 開頭的字串常值。"""
    literal = re.compile(r"""\b(?:[rRbBfF]{0,2})["'](?:videos|projects)/""")
    offenders = [
        f"{path.relative_to(APP_DIR)}:{n}"
        for path in APP_DIR.rglob("*.py") if path.name != "keys.py"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if literal.search(line)
    ]
    assert offenders == []
