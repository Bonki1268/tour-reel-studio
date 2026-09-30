"""物件儲存的記憶體實作（spec 0006 待決事項 3；S09 補上 S3 實作與預簽網址）。"""


class MemoryStorage:
    async def put(self, key: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    async def get(self, key: str) -> bytes:
        raise NotImplementedError

    async def exists(self, key: str) -> bool:
        raise NotImplementedError
