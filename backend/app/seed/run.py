"""Demo 種子腳本（spec 0017）：python -m app.seed.run。"""

from dataclasses import dataclass, field
from pathlib import Path

from app.domain.ports import Repositories, Storage


@dataclass
class SeedResult:
    project_id: str
    created: dict[str, int] = field(default_factory=dict)
    reused: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    refresh_failed: bool = False


def project_id_for(name: str) -> str:
    raise NotImplementedError


async def seed(
    demo_dir: Path, cache_dir: Path, repos: Repositories, storage: Storage, *,
    refresh: bool = False, api_key: str | None = None,
) -> SeedResult:
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError
