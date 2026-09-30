"""路由共用的依賴。"""

from typing import Annotated

from fastapi import Depends, Request

from app.api.services import AppServices, build_services

DEMO_USER = "demo"  # MVP 單一 Demo 帳號（spec 0008 範圍外：登入與權限）


def get_services(request: Request) -> AppServices:
    """測試注入的服務；未注入時於第一次使用時依設定建立。"""
    services: AppServices | None = request.app.state.services
    if services is None:
        services = request.app.state.services = build_services(request.app.state.settings)
    return services


Services = Annotated[AppServices, Depends(get_services)]
