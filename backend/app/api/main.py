"""FastAPI 應用程式進入點。"""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.errors import HANDLED, error_response
from app.api.routes import projects, videos, webhooks
from app.api.services import AppServices
from app.config import Settings, load_settings


async def _handled(request: Request, exc: Exception) -> JSONResponse:
    status, body = error_response(exc)
    return JSONResponse(body, status)


async def _validation(request: Request, exc: Exception) -> JSONResponse:
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    return JSONResponse(
        {"code": "validation_error", "message": "請求內容不正確", "errors": jsonable_encoder(errors)}, 422
    )


def create_app(settings: Settings | None = None, services: AppServices | None = None) -> FastAPI:
    """services 未提供時依設定建立（正式環境）；測試注入記憶體版。"""
    app = FastAPI(title="Tour Reel Studio")
    app.state.settings = settings or load_settings()
    app.state.services = services

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for exc_type in HANDLED:
        app.add_exception_handler(exc_type, _handled)
    app.add_exception_handler(RequestValidationError, _validation)
    app.include_router(projects.router)
    app.include_router(videos.router)
    app.include_router(webhooks.router)
    return app
