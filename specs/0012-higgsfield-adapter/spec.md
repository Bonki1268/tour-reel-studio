# Higgsfield adapter

狀態： approved
版本：v1
關聯開發步驟：S12
核准者／時間：bonki

<!--
規則（spec-driven-development.md §4.1）：
- 「狀態」「核准者／時間」只能由使用者修改；Claude Code 只能產生 draft。
- 需求格式：- R-001：<使用者可觀察的行為>
- 驗收條件格式：- AC-001（對應 R-001）：Given / When / Then 或可量測條件
- 「驗收對應」把每個 AC 對應到 features/ 中本步驟的場景編號；本步驟每個非 external 場景都必須被至少一個 AC 對應。
- 自檢：python3 scripts/tdd.py spec
-->

## 問題與目標

S06 的生成工作與 S07 的編排目前只接 `FakeProvider`。本步驟以 Higgsfield API 實作 `ImageProvider`、`VideoProvider`、`ResultSource`，讓同一套工作流程（送出 → 輪詢 → 轉存 → 記帳）能接上真實供應商：關鍵幀用 `HF_IMAGE_MODEL` 精修 S11 的粗合成圖，影片用 `HF_VIDEO_MODEL` 把關鍵幀轉成無音訊的影片段。同時提供 `POST /webhooks/higgsfield`，只接受帶有效簽章的通知。

所有測試以 HTTP mock 進行；真實 API 只在 S12-08（external）且經使用者同意時呼叫。

### 已查證的 Higgsfield 行為（2026-10-01 閱讀 docs.higgsfield.ai 與 S00 實測）

- 送出：`POST {base}/{model}`，body 為模型參數 JSON；回應 `{status, request_id, status_url, cancel_url}`。驗證標頭 `Authorization: Key <key-id>:<key-secret>`。
- 查詢：`GET {base}/requests/{request_id}/status`；狀態 `queued`、`in_progress`、`completed`、`failed`、`nsfw`、`canceled`；完成時圖片在 `images[].url`、影片在 `video.url`。狀態回應**沒有點數欄位**。
- 上傳輸入圖：`POST {base}/files/generate-upload-url {content_type}` → `{public_url, upload_url, upload_headers}`，再 `PUT upload_url`（官方 SDK 與 S00 的做法）。
- webhook：送出時以查詢參數 `hf_webhook=<url>` 註冊；payload `{request_id, status, error, payload}`；5xx 會重送最多兩小時、可能重複送達。**官方 webhook 沒有簽章機制**（見待決事項 1）。
- 錯誤：文件建議送出時帶 `Idempotency-Key`；並行數超過上限時回 **400**（訊息含 "concurrent requests"），沒有 `Retry-After`。

## 範圍內／範圍外

**範圍內**
- `backend/app/providers/higgsfield.py`：`HiggsfieldProvider`（同時實作 `ImageProvider`、`VideoProvider`、`ResultSource`），以 `httpx.AsyncClient` 直接呼叫
- 輸入轉換：S11 `ComposeRequest.to_input()` 與影片工作的 `{keyframe_key, prompt}` 中的自有儲存 key → 從 `Storage` 讀出 → 上傳至 Higgsfield 取得網址 → 組成模型參數
- 狀態對應、成本欄位解析、錯誤分類、結果下載
- webhook：產生帶簽章的回呼網址、`POST /webhooks/higgsfield` 驗證簽章
- 日誌遮蔽 API 金鑰
- 關鍵幀工作接上 B1：編排在送出關鍵幀工作前產生粗合成圖與遮罩、存入自有儲存，關鍵幀工作輸入改為 S11 的精修合成請求（S11 spec 範圍外第 2 點，見待決事項 3）
- 新設定：`HIGGSFIELD_BASE_URL`、`HIGGSFIELD_WEBHOOK_SECRET`、`PUBLIC_BASE_URL`；`build_services` 在 `HIGGSFIELD_API_KEY` 有值時使用本 adapter

**範圍外**
- webhook 收到後提早喚醒輪詢、重複通知去重、Worker 重啟接續（S18）
- 實際扣點對帳（狀態回應沒有點數；成本記帳沿用 S04 估價，見待決事項 4）
- 9:16 裁切／縮圖（S17 種子資料）
- 部署與 HTTPS 反向代理

## 使用者旅程

1. 業者核准企劃後，Worker 依每鏡擺放產生粗合成圖，送 Higgsfield 精修成關鍵幀，再送圖生影片。
2. Worker 每隔設定秒數查詢狀態；完成後立刻把結果下載到自有儲存，資料庫只留自有路徑，業者之後看到的都是自有儲存的預簽名網址。
3. Higgsfield 暫時過載（429／5xx）時工作自動重試一次；輸入錯誤或金鑰錯誤時不重試，直接標示該鏡失敗。
4. 有人偽造 webhook 呼叫時，系統回 401，不碰任何生成工作。

## 需求

- R-001：圖生影片工作以設定檔的 `HF_VIDEO_MODEL` 送出，請求帶入關鍵幀網址（由自有儲存上傳到 Higgsfield 取得）與影片提示詞，明確關閉音訊生成，並回傳包含 Higgsfield `request_id` 作為 `external_id` 的 `ProviderJob`。
- R-002：精修合成工作以設定檔的 `HF_IMAGE_MODEL` 送出，以粗合成圖為第一張參考圖、身份板為第二張，提示詞沿用 S11 的精修提示詞，輸出 9:16；回傳包含 `external_id` 的 `ProviderJob`。
- R-003：查詢工作狀態時，把 Higgsfield 狀態對應為內部狀態：`queued`、`in_progress` → `running`；`completed` → `succeeded` 並帶出結果網址；`failed`、`nsfw`、`canceled` → `failed`（不可重試，訊息標明原因）；回應若含點數或成本欄位則解析為 `actual_cost`，缺少時為 `None`。
- R-004：取得結果後立即下載結果檔並存入自有物件儲存；生成工作與鏡頭版本只記錄自有儲存路徑，不記錄 Higgsfield 結果網址。
- R-005：`POST /webhooks/higgsfield` 只接受帶有效簽章的呼叫；簽章缺少或錯誤時回 401 且不讀取、不更新任何生成工作；簽章有效時回 202（本步驟只確認收到，工作狀態仍以輪詢結果為準）。`WEBHOOK_ENABLED` 為真且設定了 `PUBLIC_BASE_URL` 時，送出請求附上帶簽章的回呼網址；否則不附。
- R-006：Higgsfield API 錯誤分類：HTTP 408、429、5xx、423、連線錯誤或逾時為可重試；400 中「並行數已達上限」為可重試；其他 4xx（含一般 400、401、403、404、422）為不可重試。錯誤訊息不含 API 金鑰與網址查詢參數。
- R-007：API 金鑰不出現在任何日誌（含 httpx 的請求日誌、錯誤訊息與例外）。
- R-008：關鍵幀工作送出前，編排依該鏡的實景照、角色去背圖與擺放參數產生粗合成圖與遮罩並存入自有儲存，關鍵幀工作輸入為 S11 精修合成請求（`base_image_key`、`mask_key`、`reference_keys`、`prompt`）；擺放參數錯誤時該鏡失敗、不送出任何供應商請求。

## 驗收條件

- AC-001（對應 R-001）：Given mock 的 Higgsfield 與存有關鍵幀的自有儲存，When 以 `{keyframe_key, prompt}` 送出圖生影片請求，Then 送出的路徑為 `HF_VIDEO_MODEL`，body 的 `image_url` 是上傳端點回傳的 `public_url`、`prompt` 為影片提示詞、`generate_audio` 為 `false`，標頭帶 `Idempotency-Key` = `provider_idempotency_key`，回傳的 `ProviderJob.external_id` 為 mock 的 `request_id`。
- AC-002（對應 R-002）：When 以 S11 `ComposeRequest.to_input()` 送出合成請求，Then 送出的路徑為 `HF_IMAGE_MODEL`，body 的 `image_urls` 依序為粗合成圖與身份板上傳後的網址、`aspect_ratio` 為 `9:16`、`prompt` 為請求中的提示詞，回傳的 `ProviderJob.external_id` 為 mock 的 `request_id`。
- AC-003（對應 R-003）：Given 查詢狀態依序回傳 `queued`、`in_progress`、`completed`，When 以 S06 的工作流程輪詢，Then 前兩次為 `running`、第三次為 `succeeded` 且結果網址為回應中的 `video.url`（圖片為 `images[0].url`）；`failed`、`nsfw`、`canceled` 對應為不可重試的 `failed`；回應沒有成本欄位時 `actual_cost` 為 `None`，有 `credits` 欄位時解析為 `Decimal`。
- AC-004（對應 R-004）：Given 一個已完成的工作，When S06 工作流程取得結果，Then 結果檔內容存於 `keys.clip(...)`（關鍵幀為 `keys.keyframe(...)`），鏡頭版本記錄的是該自有路徑，生成工作與鏡頭版本的任何欄位都不含 Higgsfield 結果網址。
- AC-005（對應 R-005）：When 以錯誤或缺少的簽章呼叫 `POST /webhooks/higgsfield`，Then 回應 401，且 repository 沒有任何讀取或更新生成工作的呼叫；When 以正確簽章呼叫，Then 回應 202。簽章驗證函式對正確、錯誤、缺少、被竄改的參考值分別回傳真、假、假、假。
- AC-006（對應 R-006）：Given Higgsfield 送出端點回應 HTTP 429、503、400、401，Then 送出拋出的 `ProviderError.retryable` 分別為真、真、假、假；400 訊息含 "concurrent requests" 時為真；連線錯誤為真。
- AC-007（對應 R-007）：Given 日誌層級為 DEBUG（含 httpx、httpcore），When 送出圖生影片請求、查詢狀態並觸發一次 401 錯誤，Then 擷取到的所有日誌與例外訊息都找不到 API 金鑰。
- AC-008（對應 R-008）：Given 一鏡有實景照、角色去背圖、身份板與擺放參數，When 編排執行該鏡，Then 自有儲存出現粗合成圖與遮罩，送給 image provider 的輸入等於 `build_compose_request(...).to_input()`；擺放參數超出範圍時該鏡失敗且 provider 沒有收到任何請求。

## 驗收對應

| AC | 場景 |
|---|---|
| AC-001 | S12-01 |
| AC-002 | S12-02 |
| AC-003 | S12-03 |
| AC-004 | S12-04 |
| AC-005 | S12-05 |
| AC-006 | S12-06 |
| AC-007 | S12-07 |
| AC-008 | S12-02 |

AC-003 的 nsfw／canceled、成本欄位，AC-005 的簽章函式，AC-006 的 408／423／並行上限，AC-008 的編排串接以單元測試驗證（見 design.md）。S12-08 為 external，不列入閘門。

## 非功能需求

- 測試不連外：所有 Higgsfield 與結果下載以 `respx` mock；儲存使用記憶體版。
- 送出（POST）不在 adapter 內自動重試，避免重複扣點；重試只由 S06 工作流程決定（每工作最多 1 次）。查詢（GET）的暫時錯誤交由 S06 的輪詢迴圈處理。
- 模型名稱只從設定讀取；金鑰只在環境變數。
- HTTP 逾時：送出與查詢 30 秒、上傳與下載 120 秒。

## 假設、風險與待決事項

1. **webhook 簽章由我方產生。** Higgsfield 官方 webhook 沒有簽章（架構書 §11 第 4 點已預期此情況：「改用隨機 token 並以輪詢結果為準」）。草稿做法：回呼網址為 `{PUBLIC_BASE_URL}/webhooks/higgsfield?ref=<provider_idempotency_key>&sig=<HMAC-SHA256(HIGGSFIELD_WEBHOOK_SECRET, ref)>`，端點以常數時間比較驗證；場景中的「簽章」即此 `sig`。有效通知在本步驟只回 202、不更新工作（輪詢為準），提早喚醒與去重留給 S18。
2. **400 的分類。** 場景要求 400 → non_retryable；但官方文件指出「並行數已達上限」也回 400。草稿把訊息含 "concurrent requests" 的 400 視為可重試，其他 400 不重試（場景的 400 沒有該訊息，仍為 non_retryable）。若不同意，可改成所有 400 一律不重試。
3. **粗合成接進編排（R-008）。** S11 spec 把這件事排到 S12；這會修改 S07 編排的關鍵幀工作輸入，並在 `storage/keys.py` 新增 `mask(video_id, shot_no, take)`（`…/take{n}/mask.png`）。需要角色去背圖、身份板與實景照的 key 已存在於資料模型（`CharacterVersion.cutout_key`、`identity_board_key`、`ScenePhoto`）。若希望 S12 只做 adapter，可把 R-008 移到 S17。
4. **成本。** 狀態回應沒有點數欄位，`actual_cost` 通常為 `None`，記帳沿用 S04 估價；若之後回應出現 `credits`／`cost` 欄位會被解析。
5. **遮罩不送給模型。** S00 選定的 `xai/grok-imagine-image-2.0` 沒有遮罩參數；遮罩只存在自有儲存與工作輸入快照，供之後改用支援遮罩的模型。
6. **冪等鍵。** 文件建議送出帶 `Idempotency-Key`（OpenAPI 尚未列出，S00 時期文件說不支援）；adapter 一律帶上 `provider_idempotency_key`，伺服器忽略時也無害。送出時連線中斷歸為可重試，若伺服器不支援冪等鍵，重試可能重複扣點——風險由 S06 每工作最多重試 1 次限制。
7. **不使用官方 SDK。** SDK 0.2.0 讀取 `HF_KEY` 環境變數、對 POST 自動重試、錯誤只留訊息不留狀態碼，無法滿足 R-006 與「POST 不重試」；改用 httpx 直接呼叫，端點與欄位以 S00 實測與官方文件為準。
8. **金鑰格式。** `HIGGSFIELD_API_KEY` 為 `key-id:key-secret`（S00 的 `HF_KEY`）。
