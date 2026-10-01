"""官網擷取快取（spec 0017 R-005）：種子腳本只讀快取檔；明確要求時才呼叫 Firecrawl 更新快取。"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"
REFRESH_TIMEOUT_S = 60.0


@dataclass
class BrandPatch:
    """擷取結果可補上的品牌欄位。"""

    colors: list[str] = field(default_factory=list)
    logo_url: str | None = None
    fonts: list[str] = field(default_factory=list)
    booking_url: str | None = None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def brand_from_firecrawl(payload: dict[str, Any]) -> BrandPatch:
    """Firecrawl branding 回應（或快取檔）→ 品牌欄位：主色依 primary、secondary、accent 排序。"""
    branding, metadata = _dict(payload.get("branding")), _dict(payload.get("metadata"))
    palette = _dict(branding.get("colors"))
    colors = [palette[k] for k in ("primary", "secondary", "accent") if isinstance(palette.get(k), str)]
    fonts = [f["family"] for f in branding.get("fonts") or [] if isinstance(f, dict) and f.get("family")]
    logo = _dict(branding.get("images")).get("logo") or branding.get("logo")
    booking = metadata.get("booking_url")
    return BrandPatch(
        colors=colors, logo_url=logo if isinstance(logo, str) else None, fonts=fonts,
        booking_url=booking if isinstance(booking, str) else None,
    )


def domain_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def cache_path(cache_dir: Path, domain: str) -> Path:
    return cache_dir / f"firecrawl-{domain}.json"


def load_cache(cache_dir: Path, domain: str) -> dict[str, Any] | None:
    path = cache_path(cache_dir, domain)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


async def refresh(cache_dir: Path, website: str, api_key: str) -> bool:
    """呼叫 Firecrawl 擷取官網品牌資訊並寫回快取；失敗時保留舊快取並回傳 False。金鑰不寫入快取與日誌。"""
    try:
        async with httpx.AsyncClient(timeout=REFRESH_TIMEOUT_S) as client:
            r = await client.post(
                FIRECRAWL_SCRAPE_URL, headers={"Authorization": f"Bearer {api_key}"},
                json={"url": website, "formats": ["branding"]},
            )
        r.raise_for_status()
        data = _dict(r.json().get("data"))
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Firecrawl 擷取失敗，沿用舊快取：%s", type(e).__name__)
        return False
    if not data.get("branding"):
        logger.warning("Firecrawl 回應沒有 branding，沿用舊快取")
        return False
    cache = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "source": "firecrawl",
        "branding": data["branding"],
        "metadata": _dict(data.get("metadata")),
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_path(cache_dir, domain_of(website)).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(cache_path(cache_dir, domain_of(website)))
    return True
