"""匯出 OpenAPI 給前端產生型別（spec 0015）：python scripts/export_openapi.py [輸出路徑]。"""

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.api.main import create_app  # noqa: E402
from app.config import Settings  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "apps" / "web" / "src" / "api" / "openapi.json"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    # 匯出 schema 不需要真的服務；services 為 None，路由不會被呼叫
    app = create_app(Settings(_env_file=None), services=None)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已匯出 {out}")


if __name__ == "__main__":
    main()
