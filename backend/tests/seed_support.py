"""S17 測試共用：以程式產生 demo 素材目錄與官網擷取快取（不依賴 seed/demo/ 的真實檔案）。"""

import io
import json
from pathlib import Path
from typing import Any

from PIL import Image

SCENE_COLORS = [(200, 80, 60), (60, 160, 90), (70, 90, 200), (220, 200, 60), (120, 60, 160)]


def jpeg(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def png(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def cutout_png(*, transparent: bool = True, bottom_margin: int = 40) -> bytes:
    """300×600 的去背圖：中間不透明人形，四周與腳底下方 bottom_margin 像素透明。"""
    image = Image.new("RGBA", (300, 600), (0, 0, 0, 0) if transparent else (255, 255, 255, 255))
    body = Image.new("RGBA", (180, 600 - 30 - bottom_margin), (150, 30, 30, 255))
    image.paste(body, (60, 30))
    return png(image)


def demo_json(name: str, n_scenes: int = 3, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": name,
        "website": "https://zeelandia-cafe.example.com",
        "tone": "歷史趣味、輕鬆親切",
        "selling_points": ["戶外露天座位", "古堡拿鐵"],
        "address": "台南市安平區 安平古堡園區內",
        "booking_url": "https://zeelandia-cafe.example.com/booking",
        "colors": ["#8B2E1F"],
        "logo": "logo.png",
        "character": {
            "name": "鄭成功",
            "anchor_zh": "鄭成功：明末武將，深紅色官袍",
            "anchor_en": "Koxinga in a deep red Ming robe",
            "identity_board": "identity_board.png",
            "cutout": "character_cutout.png",
        },
        "scenes": [
            {"file": f"scene-{n}.jpg", "description_zh": f"實景 {n}", "description_en": f"scene {n}"}
            for n in range(1, n_scenes + 1)
        ],
    }
    data.update(overrides)
    return data


def write_demo(demo_dir: Path, name: str, n_scenes: int = 3, **overrides: Any) -> dict[str, Any]:
    """在 demo_dir 寫入 demo.json 與所有圖片；實景照為 3000×4000 的單色 JPEG。"""
    demo_dir.mkdir(parents=True, exist_ok=True)
    data = demo_json(name, n_scenes, **overrides)
    (demo_dir / "demo.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (demo_dir / "logo.png").write_bytes(png(Image.new("RGBA", (200, 200), (139, 46, 31, 255))))
    (demo_dir / "identity_board.png").write_bytes(png(Image.new("RGB", (1200, 800), (240, 240, 240))))
    (demo_dir / "character_cutout.png").write_bytes(cutout_png())
    for i in range(len(data["scenes"])):
        (demo_dir / f"scene-{i + 1}.jpg").write_bytes(jpeg((3000, 4000), SCENE_COLORS[i % len(SCENE_COLORS)]))
    return data


def cache_payload() -> dict[str, Any]:
    """手動建立的官網擷取快取（格式同 Firecrawl branding 回應）。"""
    return {
        "fetched_at": "2026-10-01T00:00:00+00:00",
        "source": "manual",
        "branding": {
            "colors": {"primary": "#1F4E8B", "secondary": "#F2E3C6", "accent": "#C9A227"},
            "fonts": [{"family": "Noto Serif TC"}, {"family": "Inter"}],
            "images": {"logo": "https://zeelandia-cafe.example.com/logo.svg", "favicon": "https://x/favicon.ico"},
        },
        "metadata": {"title": "古堡咖啡", "booking_url": "https://cache.example.com/booking"},
    }


def write_cache(cache_dir: Path, domain: str = "zeelandia-cafe.example.com") -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"firecrawl-{domain}.json"
    path.write_text(json.dumps(cache_payload(), ensure_ascii=False), encoding="utf-8")
    return path
