"""物件儲存（spec 0006、0008、0009）：記憶體實作供測試，S3 實作供 MinIO／R2／S3。"""

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import Settings
from app.domain.ports import PresignedUrl
from app.domain.video import utc_now

if TYPE_CHECKING:  # boto3-stubs 只在開發依賴中
    from mypy_boto3_s3 import S3Client


class ObjectNotFound(KeyError):
    """物件不存在。"""

    def __str__(self) -> str:
        return f"物件不存在：{self.args[0]}" if self.args else "物件不存在"


class MemoryStorage:
    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self._objects[key] = (bytes(data), content_type)

    async def get(self, key: str) -> bytes:
        try:
            return self._objects[key][0]
        except KeyError:
            raise ObjectNotFound(key) from None

    async def exists(self, key: str) -> bool:
        return key in self._objects

    async def presign_put(self, key: str, ttl_s: int, content_type: str) -> PresignedUrl:
        """測試用網址：memory://<key>?upload&expires=<epoch 秒>。"""
        expires_at = utc_now() + timedelta(seconds=ttl_s)
        return PresignedUrl(f"memory://{key}?upload&expires={int(expires_at.timestamp())}", expires_at)

    async def presign_get(self, key: str, ttl_s: int) -> PresignedUrl:
        """測試用網址：memory://<key>?expires=<epoch 秒>。"""
        if key not in self._objects:
            raise ObjectNotFound(key)
        expires_at = utc_now() + timedelta(seconds=ttl_s)
        return PresignedUrl(f"memory://{key}?expires={int(expires_at.timestamp())}", expires_at)


def _client(settings: Settings, endpoint_url: str) -> "S3Client":
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        region_name=settings.s3_region,
        # MinIO 需要 path style；s3v4 讓 R2／S3／MinIO 的預簽名網址一致
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _is_not_found(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound")


class S3Storage:
    """S3 相容儲存（MinIO／R2／S3）；boto3 的同步呼叫在執行緒中執行（spec 0009）。"""

    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self._client = _client(settings, settings.s3_endpoint_url)
        # 預簽名網址給瀏覽器使用：docker 內部與外部位址不同時，以公開位址簽章
        self._presigner = _client(settings, settings.s3_public_endpoint_url or settings.s3_endpoint_url)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )

    async def get(self, key: str) -> bytes:
        def read() -> bytes:
            try:
                return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            except ClientError as e:
                if _is_not_found(e):
                    raise ObjectNotFound(key) from None
                raise

        return await asyncio.to_thread(read)

    async def exists(self, key: str) -> bool:
        def head() -> bool:
            try:
                self._client.head_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError as e:
                if _is_not_found(e):
                    return False
                raise

        return await asyncio.to_thread(head)

    async def presign_get(self, key: str, ttl_s: int) -> PresignedUrl:
        expires_at = utc_now() + timedelta(seconds=ttl_s)
        url = self._presigner.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=ttl_s
        )
        return PresignedUrl(url, expires_at)

    async def presign_put(self, key: str, ttl_s: int, content_type: str) -> PresignedUrl:
        """上傳時需帶相同的 Content-Type 標頭。"""
        expires_at = utc_now() + timedelta(seconds=ttl_s)
        url = self._presigner.generate_presigned_url(
            "put_object", Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=ttl_s,
        )
        return PresignedUrl(url, expires_at)
