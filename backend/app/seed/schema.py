"""種子資料 schema（spec 0017 R-007）：demo.json 的 Pydantic 模型與素材目錄驗證。"""

from pathlib import Path

from pydantic import BaseModel


class SeedError(Exception):
    """種子資料驗證失敗；problems 列出所有問題。"""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


class SeedCharacter(BaseModel):
    name: str
    anchor_zh: str
    anchor_en: str
    identity_board: str
    cutout: str


class SeedScene(BaseModel):
    file: str
    description_zh: str
    description_en: str = ""


class SeedDemo(BaseModel):
    name: str
    website: str | None = None
    tone: str = ""
    selling_points: list[str] = []
    address: str = ""
    booking_url: str | None = None
    colors: list[str] = []
    logo: str | None = None
    character: SeedCharacter
    scenes: list[SeedScene]


def validate_dir(demo_dir: Path) -> tuple[SeedDemo | None, list[str]]:
    raise NotImplementedError
