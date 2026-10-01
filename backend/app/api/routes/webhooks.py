"""POST /webhooks/higgsfield（spec 0012、0018）：驗證簽章後排入 Worker 立即查詢；不採用通知內容。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.deps import Services
from app.config import Settings
from app.jobs.recovery import UNFINISHED, video_of
from app.providers.webhook import WEBHOOK_PATH, verify_request

router = APIRouter()


@router.post(WEBHOOK_PATH)
async def higgsfield_webhook(request: Request, svc: Services) -> JSONResponse:
    settings: Settings = request.app.state.settings
    params = request.query_params
    ref = params.get("ref")
    if not verify_request(settings, ref, params.get("sig")):
        return JSONResponse({"code": "invalid_signature", "message": "webhook 簽章無效"}, 401)
    # 不以 payload 更新工作，避免偽造或重放結果：由 Worker 向供應商查詢後以條件更新處理（只處理一次）
    job = await svc.repos.jobs.get_by_provider_key(ref or "")
    if job is not None and job.status in UNFINISHED:
        video_id = await video_of(svc.repos, job)
        if video_id is not None:
            await svc.queue.enqueue("process_webhook", video_id=video_id, job_id=job.id)
    return JSONResponse({"accepted": True}, 202)
