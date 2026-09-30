"""FastAPI 應用程式進入點。"""

from fastapi import FastAPI

from app.api.services import AppServices
from app.config import Settings, load_settings


def create_app(settings: Settings | None = None, services: AppServices | None = None) -> FastAPI:
    """services 未提供時依設定建立（正式環境）；測試注入記憶體版。"""
    app = FastAPI(title="Tour Reel Studio")
    app.state.settings = settings or load_settings()
    app.state.services = services

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
