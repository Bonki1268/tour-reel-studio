"""FastAPI 應用程式進入點。"""

from fastapi import FastAPI

from app.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    raise NotImplementedError
