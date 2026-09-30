# 物件儲存：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
infra/docker-compose.test.yml   新增 minio（bitnamilegacy/minio:2025.5.24，埠 59000，預設建立 trs-test 儲存桶）
backend/app/
├─ storage/keys.py      架構書 §7 路徑函式＋參數驗證
├─ storage/objects.py   MemoryStorage（補 presign_put）、S3Storage、ObjectNotFound
├─ domain/ports.py      Storage 介面補 presign_put
├─ jobs/generation.py   result_key 改用 keys.keyframe／keys.clip
├─ jobs/orchestrator.py 成品路徑改用 keys.render
├─ api/services.py      build_services 使用 S3Storage
└─ config.py            s3_endpoint_url、s3_public_endpoint_url、s3_bucket、s3_access_key_id、s3_secret_access_key、s3_region
```

新增依賴：`boto3`（dev：`boto3-stubs[s3]` 供 mypy）。

### 路徑（`app/storage/keys.py`，架構書 §7）

```python
def brand_logo(project_id) -> "projects/{project_id}/brand/logo.png"
def identity_board(project_id, char_id, version) -> "projects/{project_id}/characters/{char_id}/v{version}/identity_board.png"
def cutout(project_id, char_id, version) -> ".../v{version}/cutout.png"
def scene_photo(project_id, photo_id) -> "projects/{project_id}/scenes/{photo_id}.jpg"
def rough(video_id, shot_no, take) -> "videos/{video_id}/shots/{shot_no}/take{take}/rough.png"
def keyframe(video_id, shot_no, take) -> ".../take{take}/keyframe.png"
def clip(video_id, shot_no, take) -> ".../take{take}/clip.mp4"
def render(video_id, render_id) -> "videos/{video_id}/renders/{render_id}.mp4"
```

- 字串參數：非空、不含 `/`、`\`，不為 `.`、`..` → 否則 `ValueError`。
- 整數參數：`bool` 以外的 `int`，且 ≥ 1 → 否則 `ValueError`。

### 儲存（`app/storage/objects.py`）

```python
class ObjectNotFound(KeyError): ...

class S3Storage:
    def __init__(self, settings: Settings) -> None   # 兩個 boto3 client：內部用 endpoint、預簽名用 public endpoint
    async def put(key, data, content_type) -> None           # put_object
    async def get(key) -> bytes                              # get_object；NoSuchKey → ObjectNotFound
    async def exists(key) -> bool                            # head_object；404 → False
    async def presign_get(key, ttl_s) -> PresignedUrl        # generate_presigned_url("get_object")
    async def presign_put(key, ttl_s, content_type) -> PresignedUrl  # ("put_object", ContentType)；上傳需帶相同 Content-Type
```

- boto3 client 以 `Config(signature_version="s3v4", s3={"addressing_style": "path"})` 建立（MinIO 需要 path style）。
- 同步呼叫以 `asyncio.to_thread` 執行。
- `MemoryStorage.get` 找不到時改拋 `ObjectNotFound`（`KeyError` 子類別，既有呼叫端不受影響）。

### 設定

| 設定 | 預設值（對應測試 compose） |
|---|---|
| `S3_ENDPOINT_URL` | `http://localhost:59000` |
| `S3_PUBLIC_ENDPOINT_URL` | 空（使用 `S3_ENDPOINT_URL`） |
| `S3_BUCKET` | `trs-test` |
| `S3_ACCESS_KEY_ID`／`S3_SECRET_ACCESS_KEY` | `trs`／`trs-secret-123`（僅本機測試容器；`SecretStr`） |
| `S3_REGION` | `us-east-1` |

## 資料模型／狀態轉換變更

無。

## API 契約（request／response、錯誤碼）

本步驟沒有新的 HTTP 端點；S08 的 `preview_url`、`download` 改由 S3 產生預簽名網址。

## 失敗行為、安全與可觀測性

- 找不到物件：`ObjectNotFound`；其他 S3 錯誤照常拋出（不重試，由呼叫端決定）。
- 錯誤訊息只含路徑，不含金鑰與簽章。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S09-01，integration） | `backend/tests/bdd/test_s09_storage.py` |
| R-002 | AC-002 | BDD（S09-02，integration） | 同上 |
| R-003 | AC-003～AC-005 | BDD（S09-03）＋Unit | 同上、`backend/tests/unit/test_keys.py` |
| R-004 | AC-006 | BDD（S09-04，integration，實際等待 2 秒） | 同上 |
| R-005 | AC-007 | Unit | `backend/tests/unit/test_s3_storage.py` |

- 整合測試連到 compose 的 MinIO；每個測試使用隨機前綴，測試結束刪除該前綴下的物件。
- 預計單元測試（≥ 1，預計約 12）：
  - `test_r003_all_paths_match_section7`、`test_r003_rejects_invalid_segments[…]`、`test_r003_rejects_invalid_numbers[…]`
  - `test_r003_no_hardcoded_paths_in_app`
  - `test_r001_memory_get_missing_raises_object_not_found`
  - `test_r005_presign_uses_public_endpoint`、`test_r005_presign_defaults_to_endpoint`、`test_r005_build_services_uses_s3`
  - `test_r002_memory_presign_put`

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：測試用 MinIO 採 `bitnamilegacy/minio:2025.5.24`（spec 待決事項 1）。
- 替代方案：`cgr.dev/chainguard/minio:latest`。
- 取捨：固定版本讓測試可重現，且能以 compose 健康檢查確認就緒；該映像不再更新，但只在本機測試使用，正式環境用 R2／S3。
- 決定：boto3 同步用戶端＋`asyncio.to_thread`。
- 取捨：依賴少、型別完整；每次呼叫佔用一個執行緒，對 MVP 的流量足夠。
