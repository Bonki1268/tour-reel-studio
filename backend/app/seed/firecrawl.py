"""官網擷取快取（spec 0017 R-005）。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"


@dataclass
class BrandPatch:
    colors: list[str] = field(default_factory=list)
    logo_url: str | None = None
    fonts: list[str] = field(default_factory=list)
    booking_url: str | None = None


def brand_from_firecrawl(payload: dict[str, Any]) -> BrandPatch:
    raise NotImplementedError


def domain_of(url: str) -> str:
    raise NotImplementedError


def load_cache(cache_dir: Path, domain: str) -> dict[str, Any] | None:
    raise NotImplementedError


async def refresh(cache_dir: Path, website: str, api_key: str) -> bool:
    raise NotImplementedError
