# Higgsfield adapter：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
backend/app/providers/higgsfield.py
├─ HiggsfieldProvider(settings, storage, http: httpx.AsyncClient | None = None)
│   ├─ compose(req) -> ProviderJob          輸入：S11 ComposeRequest.to_input()
│   ├─ image_to_video(req) -> ProviderJob   輸入：{keyframe_key, prompt, ...}
│   ├─ fetch_result(job) -> ProviderResult  GET /requests/{id}/status
│   └─ download(result) -> (bytes, content_type)
├─ map_status(body) -> ProviderResult        純函式：狀態對應＋結果網址＋成本欄位
├─ parse_cost(body) -> Decimal | None
├─ classify(status_code, body) -> bool       是否可重試
├─ compose_args(...) / i2v_args(...)         模型參數（沿用 S00 pipeline.py）
└─ RedactSecrets(logging.Filter)             把金鑰替換成 ***

backend/app/providers/webhook.py
├─ callback_url(settings, ref) -> str | None
├─ sign(secret, ref) -> str                 HMAC-SHA256 hex
└─ verify(secret, ref, sig) -> bool          hmac.compare_digest；任何缺少都回傳 False

backend/app/api/routes/webhooks.py           POST /webhooks/higgsfield
```

### 送出流程

1. 從 `req.input` 取出自有儲存 key → `storage.get(key)` → 上傳到 Higgsfield（`POST /files/generate-upload-url` → `PUT upload_url`）取得 `public_url`。
2. 組參數：
   - 合成：`{"prompt", "image_urls": [rough, identity...], "aspect_ratio": "9:16", "resolution": "1k", "quality": "medium"}`（遮罩不送，見 spec 待決 5）
   - 影片：`{"image_url", "prompt", "duration", "resolution": "720p", "output_format": "mp4", "generate_audio": false}`；`duration` 取自輸入，預設 4（Seedance 最短 4 秒，S00）
3. `POST {base}/{model}[?hf_webhook=<callback>]`，標頭 `Authorization: Key …`、`Idempotency-Key: <provider_idempotency_key>`；adapter 內不重試。
4. 回傳 `ProviderJob(provider="higgsfield", model, external_id=request_id)`。

### 狀態對應

| Higgsfield | 內部 | 備註 |
|---|---|---|
| queued、in_progress | running | |
| completed | succeeded | `video.url` 或 `images[0].url`；缺網址 → failed（可重試） |
| failed | failed（不可重試） | 訊息帶 `error` |
| nsfw | failed（不可重試） | 「內容審核拒絕」 |
| canceled | failed（不可重試） | |
| 其他值 | failed（不可重試） | 「未知狀態」 |

成本：body 中 `credits`、`cost`（數字或數字字串）→ `Decimal`；缺少或無法解析 → `None`。

### 錯誤分類

`retryable = status in {408, 423, 429} or status >= 500 or (status == 400 and "concurrent requests" in detail)`；`httpx.TimeoutException`、`httpx.TransportError` → 可重試。錯誤訊息只含狀態碼與 `detail`（截斷 300 字），不含請求標頭或網址查詢參數。

### 日誌

- adapter 不記錄請求標頭；`RedactSecrets` 掛在 `app` 啟動與 Worker 啟動時的 root handlers，以及 `httpx`、`httpcore` logger，替換所有出現的金鑰（含 key-id 與 secret 兩段）。
- 例外訊息由 `classify` 組成，不含金鑰。

### 編排串接（R-008）

`QuickModeOrchestrator._run_shot`（S07）在關鍵幀工作前：
1. 讀實景照（`ScenePhoto.key`）、鎖定的角色版本（`cutout_key`、`identity_board_key`）。
2. `Placement.from_mapping(shot.placement)` → `composite(...)` → `storage.put(keys.rough(...))`、`storage.put(keys.mask(...))`。
3. `JobSpec.input_snapshot = {"shot_no", **build_compose_request(...).to_input()}`。
4. `PlacementError` 或缺少素材 → 該鏡發布 `shot_failed`、影片進入 `needs_attention`（沿用 S07 的鏡頭失敗流程），不送出。

`FakeProvider` 不讀輸入內容，S07～S11 既有測試行為不變；S07 的測試資料需補上去背圖、身份板與實景照物件。

## 資料模型／狀態轉換變更

- 無資料表變更。`storage/keys.py` 新增 `mask(video_id, shot_no, take)`。
- `Settings` 新增 `higgsfield_base_url`（預設 `https://api.higgsfield.ai`）、`higgsfield_webhook_secret: SecretStr | None`、`public_base_url: str = ""`；`tests/conftest.py` 的隔離清單同步加入。

## API 契約（request／response、錯誤碼）

`POST /webhooks/higgsfield?ref=<provider_idempotency_key>&sig=<hex>`

| 情況 | 回應 |
|---|---|
| `sig` 或 `ref` 缺少、驗證失敗、未設定 `HIGGSFIELD_WEBHOOK_SECRET` | 401 `{"code": "invalid_signature", "message": "webhook 簽章無效"}` |
| 驗證成功 | 202 `{"accepted": true}`（不解析 body 內容以外的動作，不更新工作） |

驗證在讀取 body 與任何 repository 呼叫之前完成。

## 失敗行為、安全與可觀測性

- 上傳、送出失敗 → `ProviderError`（分類如上），由 S06 決定是否重試。
- 下載結果失敗 → S06 `_store` 已視為可重試。
- webhook 只信任簽章；即使簽章有效，也不以 payload 更新工作（防止重放偽造結果）。
- 金鑰：`SecretStr` 保存，只在組標頭時取值；`RedactSecrets` 防止第三方套件記錄。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S12-01）＋Unit | `backend/tests/bdd/test_s12_higgsfield.py`、`backend/tests/unit/test_higgsfield.py` |
| R-002 | AC-002 | BDD（S12-02）＋Unit | 同上 |
| R-003 | AC-003 | BDD（S12-03）＋Unit | 同上 |
| R-004 | AC-004 | BDD（S12-04） | 同上 |
| R-005 | AC-005 | BDD（S12-05）＋Unit | 同上、`backend/tests/unit/test_webhook.py` |
| R-006 | AC-006 | BDD（S12-06）＋Unit | 同上 |
| R-007 | AC-007 | BDD（S12-07） | 同上 |
| R-008 | AC-008 | Unit | `backend/tests/unit/test_orchestrator_b1.py` |
| — | S12-08 | external | `backend/tests/external/test_higgsfield_live.py`（不列入閘門，需使用者同意） |

- HTTP 一律以 `respx` mock（`base_url` 指向 `https://hf.test`），結果下載也 mock；`tests/higgsfield_support.py` 提供 mock 路由與回應。
- S12-03、S12-04 以 S06 `run_generation_job` 搭配 `HiggsfieldProvider`、記憶體 repository 與記憶體儲存執行（`sleep` 注入為不等待）。
- S12-05 以 FastAPI TestClient；repository 以記錄呼叫的包裝檢查沒有任何讀寫。

預計單元測試（≥ 3，預計約 20）：
- `test_r001_i2v_args_disable_audio`、`test_r001_sends_idempotency_key`、`test_r001_webhook_param_only_when_enabled`
- `test_r002_compose_args_order_and_ratio`、`test_r002_mask_not_uploaded`
- `test_r003_status_mapping[queued|in_progress|completed|failed|nsfw|canceled|unknown]`、`test_r003_image_result_url`、`test_r003_completed_without_url_fails`、`test_r003_cost_parsed`、`test_r003_cost_missing_is_none`
- `test_r005_verify_signature[valid|wrong|missing|tampered_ref]`、`test_r005_no_secret_rejects_all`、`test_r005_valid_signature_accepted`
- `test_r006_classify[408|423|429|500|503|400|400_concurrency|401|403|404|422]`、`test_r006_transport_error_retryable`、`test_r006_error_message_excludes_key`
- `test_r008_keyframe_input_is_compose_request`、`test_r008_invalid_placement_fails_without_submit`

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：以 httpx 直接實作 Higgsfield adapter（不使用官方 SDK）；webhook 以我方 HMAC 簽章的回呼網址驗證，工作狀態一律以輪詢為準；輸入圖由自有儲存讀出後上傳到 Higgsfield。
- 替代方案：官方 SDK；以 MinIO 預簽名網址當輸入（Higgsfield 必須能連到儲存，開發環境不可行）；以 webhook payload 直接更新工作。
- 取捨：直接呼叫需自行維護端點與欄位，但能控制 POST 不重試、保留狀態碼做錯誤分類、以 respx 測試；上傳多一次網路往返，但不需公開自有儲存；webhook 不更新工作，換來無法以偽造或重放通知竄改結果，代價是完成通知要等下一次輪詢（S18 再優化）。
