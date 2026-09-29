"""FastAPI 應用程式進入點。"""

from fastapi import FastAPI

from app.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Tour Reel Studio")
    app.state.settings = settings or load_settings()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
