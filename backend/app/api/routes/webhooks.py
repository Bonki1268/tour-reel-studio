"""POST /webhooks/higgsfield（spec 0012）：只驗證簽章；工作狀態一律以輪詢結果為準。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.providers.webhook import WEBHOOK_PATH, verify_request

router = APIRouter()


@router.post(WEBHOOK_PATH)
async def higgsfield_webhook(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    params = request.query_params
    if not verify_request(settings, params.get("ref"), params.get("sig")):
        return JSONResponse({"code": "invalid_signature", "message": "webhook 簽章無效"}, 401)
    # 提早喚醒輪詢與重複通知去重留給 S18；不以 payload 更新工作，避免偽造或重放結果
    return JSONResponse({"accepted": True}, 202)
