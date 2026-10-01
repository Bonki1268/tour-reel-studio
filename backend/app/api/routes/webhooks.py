"""POST /webhooks/higgsfield（spec 0012）。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/webhooks/higgsfield")
async def higgsfield_webhook(request: Request) -> JSONResponse:
    raise NotImplementedError
