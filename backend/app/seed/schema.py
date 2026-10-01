"""種子資料 schema（spec 0017 R-007）：demo.json 的 Pydantic 模型與素材目錄驗證。"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.seed.assets import has_transparent_background

MIN_SCENES, MAX_SCENES = 3, 5


class SeedError(Exception):
    """種子資料驗證失敗；problems 列出所有問題。"""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


NonEmpty = Field(min_length=1)


class SeedCharacter(BaseModel):
    name: str = NonEmpty
    anchor_zh: str = NonEmpty
    anchor_en: str = NonEmpty
    identity_board: str = NonEmpty
    cutout: str = NonEmpty


class SeedScene(BaseModel):
    file: str = NonEmpty
    description_zh: str = NonEmpty
    description_en: str = ""


class SeedDemo(BaseModel):
    name: str = NonEmpty
    website: str | None = None
    tone: str = ""
    selling_points: list[str] = []
    address: str = ""
    booking_url: str | None = None
    colors: list[str] = []
    logo: str | None = None
    character: SeedCharacter
    scenes: list[SeedScene]


def _files(raw: dict[str, Any]) -> list[str]:
    """demo.json 引用的圖片檔名（schema 不合法時盡量取出，以便一次列出所有問題）。"""
    names: list[Any] = [raw.get("logo")]
    character = raw.get("character")
    if isinstance(character, dict):
        names += [character.get("identity_board"), character.get("cutout")]
    scenes = raw.get("scenes")
    if isinstance(scenes, list):
        names += [s.get("file") for s in scenes if isinstance(s, dict)]
    return [n for n in names if isinstance(n, str) and n]


def validate_dir(demo_dir: Path) -> tuple[SeedDemo | None, list[str]]:
    """驗證 demo.json 與素材檔；回傳 (模型, 問題清單)，有任何問題時模型為 None。"""
    path = demo_dir / "demo.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"找不到 {path}"]
    except json.JSONDecodeError as e:
        return None, [f"demo.json 不是合法的 JSON：{e}"]
    if not isinstance(raw, dict):
        return None, ["demo.json 必須是 JSON 物件"]

    problems: list[str] = []
    demo: SeedDemo | None = None
    try:
        demo = SeedDemo.model_validate(raw)
    except ValidationError as e:
        problems += [f"demo.json 欄位 {'.'.join(map(str, err['loc']))}：{err['msg']}" for err in e.errors()]

    scenes = raw.get("scenes")
    if isinstance(scenes, list) and not MIN_SCENES <= len(scenes) <= MAX_SCENES:
        problems.append(f"實景照需要 {MIN_SCENES} 到 {MAX_SCENES} 張，目前 {len(scenes)} 張")

    for name in _files(raw):
        if not (demo_dir / name).is_file():
            problems.append(f"圖片檔不存在：{name}")

    character = raw.get("character")
    cutout = character.get("cutout") if isinstance(character, dict) else None
    if isinstance(cutout, str) and (demo_dir / cutout).is_file():
        if not has_transparent_background((demo_dir / cutout).read_bytes()):
            problems.append(f"去背圖 {cutout} 沒有透明背景（四個角落需完全透明）")

    return (demo if not problems else None), problems
