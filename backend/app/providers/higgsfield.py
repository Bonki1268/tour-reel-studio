"""Higgsfield adapter：ImageProvider、VideoProvider、ResultSource 的真實實作（架構書 §5.5；spec 0012）。

以 httpx 直接呼叫（不使用官方 SDK）：送出（POST）不自動重試，重試只由 S06 工作流程決定。
輸入圖以自有儲存 key 傳入，送出前讀出並上傳到 Higgsfield 取得網址。
"""

import logging
import math
import mimetypes
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.config import Settings
from app.domain.ports import Storage
from app.providers.base import ProviderError, ProviderJob, ProviderRequest, ProviderResult
from app.providers.webhook import callback_url
from app.storage.objects import ObjectNotFound

PROVIDER_NAME = "higgsfield"
API_TIMEOUT_S = 30.0
TRANSFER_TIMEOUT_S = 120.0
MIN_VIDEO_S = 4  # Seedance 2.5 最短 4 秒（S00）
_RETRYABLE_STATUS = {408, 423, 429}
_FAILED_MESSAGES = {
    "failed": "Higgsfield 生成失敗",
    "nsfw": "內容審核拒絕（nsfw）",
    "canceled": "請求已取消",
}
_URL_QUERY = re.compile(r"(https?://[^\s?]+)\?\S*")

logger = logging.getLogger(__name__)


def classify(status_code: int, detail: str = "") -> bool:
    """HTTP 錯誤是否可重試：暫時性錯誤與並行數上限（官方以 400 回報）可重試，其他 4xx 不重試。"""
    if status_code in _RETRYABLE_STATUS or status_code >= 500:
        return True
    return status_code == 400 and "concurrent requests" in detail.lower()


def parse_cost(body: Mapping[str, Any]) -> Decimal | None:
    """狀態回應目前沒有點數欄位；若出現 credits／cost 則解析，無法解析時回傳 None。"""
    for name in ("credits", "cost"):
        value = body.get(name)
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            continue
        try:
            cost = Decimal(str(value))
        except InvalidOperation:
            continue
        if cost.is_finite():
            return cost
    return None


def _result_url(body: Mapping[str, Any]) -> str | None:
    video = body.get("video")
    if isinstance(video, Mapping) and video.get("url"):
        return str(video["url"])
    images = body.get("images")
    if isinstance(images, list) and images and isinstance(images[0], Mapping) and images[0].get("url"):
        return str(images[0]["url"])
    return None


def map_status(body: Mapping[str, Any]) -> ProviderResult:
    """Higgsfield 狀態回應 → 內部 ProviderResult。"""
    status = body.get("status")
    if status in ("queued", "in_progress"):
        return ProviderResult("running")
    if status == "completed":
        url = _result_url(body)
        if url is None:
            return ProviderResult("failed", error=ProviderError("Higgsfield 回報完成但沒有結果網址"))
        return ProviderResult("succeeded", url=url, actual_cost=parse_cost(body))
    message = _FAILED_MESSAGES.get(str(status), f"Higgsfield 未知狀態：{status!r}")
    if body.get("error"):
        message = f"{message}：{body['error']}"
    return ProviderResult("failed", error=ProviderError(message, retryable=False))


def compose_args(prompt: str, image_urls: list[str]) -> dict[str, Any]:
    """精修合成參數（S00 選定 grok-imagine-image-2.0）：第一張為粗合成圖，其後為身份參考。"""
    return {
        "prompt": prompt,
        "image_urls": image_urls,
        "aspect_ratio": "9:16",
        "resolution": "1k",
        "quality": "medium",
    }


def i2v_args(image_url: str, prompt: str, duration: int) -> dict[str, Any]:
    return {
        "image_url": image_url,
        "prompt": prompt,
        "duration": duration,
        "resolution": "720p",
        "output_format": "mp4",
        "generate_audio": False,  # 架構書 §5.5：不生成語音
    }


def _duration(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return MIN_VIDEO_S
    return max(MIN_VIDEO_S, int(math.ceil(value)))


class RedactSecrets(logging.Filter):
    """把日誌中出現的秘密字串替換成 ***。"""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self.secrets: set[str] = {s for s in secrets if s}

    def redact(self, text: str) -> str:
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, "***")
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.redact(message)
        if redacted != message:
            record.msg, record.args = redacted, None
        return True


_LOGGERS = ("httpx", "httpcore", "app")


def _secret_parts(secret: str) -> list[str]:
    return [secret, *secret.split(":")] if secret else []


def install_redaction(secret: str) -> None:
    """在 httpx、httpcore、app 與 root handlers 掛上遮蔽過濾器（重複呼叫只會擴充同一個過濾器）。"""
    parts = _secret_parts(secret)
    targets: list[logging.Filterer] = [logging.getLogger(n) for n in _LOGGERS]
    targets += logging.getLogger().handlers
    for target in targets:
        existing = next((f for f in target.filters if isinstance(f, RedactSecrets)), None)
        if existing is None:
            target.addFilter(RedactSecrets(parts))
        else:
            existing.secrets.update(p for p in parts if p)


class HiggsfieldProvider:
    def __init__(self, settings: Settings, storage: Storage, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.storage = storage
        self.http = http
        key = settings.higgsfield_api_key
        self._key = key.get_secret_value() if key is not None else ""
        self._redactor = RedactSecrets(_secret_parts(self._key))
        install_redaction(self._key)

    @property
    def _base(self) -> str:
        return self.settings.higgsfield_base_url.rstrip("/")

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Key {self._key}"}

    # HTTP

    async def _send(self, method: str, url: str, *, timeout: float, **kw: Any) -> httpx.Response:
        try:
            if self.http is not None:
                response = await self.http.request(method, url, timeout=timeout, **kw)
            else:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    response = await client.request(method, url, **kw)
        except httpx.HTTPError as e:  # 連線錯誤、逾時
            raise ProviderError(self._clean(f"Higgsfield 連線失敗：{type(e).__name__}: {e}")) from None
        if response.is_success:
            return response
        detail = self._clean(_detail(response))[:300]
        raise ProviderError(
            f"Higgsfield HTTP {response.status_code}: {detail}",
            retryable=classify(response.status_code, detail),
        )

    def _clean(self, text: str) -> str:
        """錯誤訊息不保留金鑰與網址查詢參數（可能含簽章）。"""
        return _URL_QUERY.sub(r"\1?<已遮蔽>", self._redactor.redact(text))

    async def _upload(self, key: str) -> str:
        try:
            data = await self.storage.get(key)
        except ObjectNotFound:
            raise ProviderError(f"找不到輸入圖：{key}", retryable=False) from None
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        r = await self._send(
            "POST", f"{self._base}/files/generate-upload-url", timeout=API_TIMEOUT_S,
            headers=self._auth(), json={"content_type": content_type},
        )
        body = r.json()
        headers = body.get("upload_headers") or {"Content-Type": content_type}
        await self._send("PUT", body["upload_url"], timeout=TRANSFER_TIMEOUT_S, content=data, headers=headers)
        return str(body["public_url"])

    async def _submit(self, req: ProviderRequest, args: Mapping[str, Any]) -> ProviderJob:
        params = {}
        hook = callback_url(self.settings, req.provider_idempotency_key)
        if hook is not None:
            params["hf_webhook"] = hook
        headers = {**self._auth(), "Idempotency-Key": req.provider_idempotency_key}
        r = await self._send(
            "POST", f"{self._base}/{req.model}", timeout=API_TIMEOUT_S, json=dict(args), params=params,
            headers=headers,
        )
        request_id = r.json().get("request_id")
        if not request_id:
            raise ProviderError("Higgsfield 送出回應缺少 request_id", retryable=False)
        logger.info("已送出 Higgsfield 請求 model=%s request_id=%s", req.model, request_id)
        return ProviderJob(provider=PROVIDER_NAME, model=req.model, external_id=str(request_id))

    # ImageProvider／VideoProvider

    async def compose(self, req: ProviderRequest) -> ProviderJob:
        """輸入為 S11 ComposeRequest.to_input()；遮罩不送出（模型沒有遮罩參數，spec 待決事項 5）。"""
        keys = [str(req.input["base_image_key"]), *(str(k) for k in req.input.get("reference_keys") or [])]
        urls = [await self._upload(k) for k in keys]
        return await self._submit(req, compose_args(str(req.input.get("prompt", "")), urls))

    async def image_to_video(self, req: ProviderRequest) -> ProviderJob:
        url = await self._upload(str(req.input["keyframe_key"]))
        args = i2v_args(url, str(req.input.get("prompt", "")), _duration(req.input.get("duration_s")))
        return await self._submit(req, args)

    # ResultSource

    async def fetch_result(self, job: ProviderJob) -> ProviderResult:
        url = f"{self._base}/requests/{job.external_id}/status"
        r = await self._send("GET", url, timeout=API_TIMEOUT_S, headers=self._auth())
        return map_status(r.json())

    async def download(self, result: ProviderResult) -> tuple[bytes, str]:
        """結果網址是 Higgsfield 的 CDN，不帶金鑰。"""
        if result.url is None:
            raise ProviderError("沒有結果可下載")
        r = await self._send("GET", result.url, timeout=TRANSFER_TIMEOUT_S)
        content_type = r.headers.get("Content-Type", "").split(";")[0].strip()
        return r.content, content_type or mimetypes.guess_type(result.url)[0] or "application/octet-stream"


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, Mapping):
        for name in ("detail", "message", "error"):
            if body.get(name):
                return str(body[name])
    return str(body)
