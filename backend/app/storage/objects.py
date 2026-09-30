"""物件儲存的記憶體實作（spec 0006 待決事項 3；S08 預簽名下載；S09 補上 S3 實作）。"""

from app.domain.ports import PresignedUrl


class MemoryStorage:
    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self._objects[key] = (bytes(data), content_type)

    async def get(self, key: str) -> bytes:
        try:
            return self._objects[key][0]
        except KeyError:
            raise KeyError(f"物件不存在：{key}") from None

    async def exists(self, key: str) -> bool:
        return key in self._objects

    async def presign_get(self, key: str, ttl_s: int) -> PresignedUrl:
        raise NotImplementedError
