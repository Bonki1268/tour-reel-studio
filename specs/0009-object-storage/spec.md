# 物件儲存

狀態：approved
版本：v1
關聯開發步驟：S09
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

實景照、角色圖、關鍵幀、鏡頭影片與成品都是大型二進位檔。S06～S08 暫時以記憶體儲存代替，API 與 Worker 是兩個程序，無法共用記憶體；正式環境也需要讓瀏覽器以短期網址直接上傳與播放，不經過 API 轉手。

本步驟以 S3 相容儲存（本機與測試用 MinIO，雲端用 R2／S3，架構書 §4）實作 `Storage` 介面，把架構書 §7 的路徑規則集中到一個模組，並以預簽名網址提供上傳與下載。

## 範圍內／範圍外

**範圍內**
- `Storage` 介面補上 `presign_put`；S3 實作 `S3Storage`（put、get、exists、presign_put、presign_get）；記憶體實作補上 `presign_put`
- `app/storage/keys.py`：架構書 §7 的全部路徑（品牌 Logo、身份板、去背圖、實景照、粗合成、關鍵幀、鏡頭影片、成品）；參數不合法時拒絕
- 既有程式改用 `keys.py`，不再自行拼接路徑（S06 的關鍵幀／影片路徑、S07 的成品路徑）
- 測試 compose 加入 MinIO；設定新增 S3 連線參數
- `build_services` 改用 `S3Storage`，API 與 Worker 共用同一個儲存

**範圍外**
- 實景照上傳的 API 端點（`POST /projects/{id}/scene-photos`，S17 以種子腳本匯入）
- 物件生命週期、CDN、Cloudflare R2 的實際部署設定

## 使用者旅程

本步驟沒有新的使用者介面。業者可觀察到的結果：

1. 生成的關鍵幀、鏡頭影片與成品在 API 與 Worker 重啟後仍存在。
2. 成品確認頁與下載使用的網址在 15 分鐘內有效，過期後需要重新取得，不會永久公開。
3. （S17 之後）瀏覽器以預簽名網址直接上傳實景照。

## 需求

- R-001：上傳的物件可以用相同路徑讀回完全相同的內容與 content type；不存在的物件讀取時明確失敗。
- R-002：以預簽名上傳網址，不需要其他憑證即可用 HTTP PUT 上傳，上傳後物件存在於儲存中。
- R-003：所有物件路徑都由 `keys.py` 依架構書 §7 產生；路徑參數為空、含 `/`、含 `..`，或版本／鏡頭／次數小於 1 時拒絕。
- R-004：預簽名下載網址在有效期內可下載，過期後被儲存拒絕；有效期由呼叫端指定。
- R-005：API 與 Worker 以相同設定連到同一個 S3 相容儲存；預簽名網址使用瀏覽器可連到的位址。

## 驗收條件

- AC-001（對應 R-001）：Given 測試用 MinIO 已啟動，When 上傳一個 PNG 檔到 `projects/p1/scenes/ph_01.jpg`，Then 讀回的位元組與上傳時相同，`exists` 為真；讀取不存在的路徑拋出 `ObjectNotFound`，`exists` 為假。
- AC-002（對應 R-002）：Given 取得 `projects/p1/scenes/ph_02.jpg` 的預簽名上傳網址，When 以 HTTP PUT（不帶任何憑證）上傳檔案，Then 回應成功，物件存在且內容相同。
- AC-003（對應 R-003）：When 產生影片 `v1` 第 1 鏡第 2 次版本的關鍵幀路徑，Then 路徑為 `videos/v1/shots/1/take2/keyframe.png`；其餘 7 種路徑與架構書 §7 完全一致。
- AC-004（對應 R-003）：路徑參數為空字串、含 `/`、為 `..` 或 `.`，或 `version`／`shot_no`／`take` 小於 1 時拋出 `ValueError`。
- AC-005（對應 R-003）：S06 的關鍵幀與鏡頭影片、S07 的成品都使用 `keys.py` 產生的路徑；程式中其他地方沒有 `videos/` 或 `projects/` 開頭的路徑字串（以測試掃描 `app/` 驗證）。
- AC-006（對應 R-004）：Given 取得有效期 1 秒的預簽名下載網址，When 等待 2 秒後下載，Then 儲存回應 403（被拒絕）；有效期內下載回應 200 且內容相同。
- AC-007（對應 R-005）：設定 `S3_PUBLIC_ENDPOINT_URL` 時預簽名網址使用該位址，未設定時使用 `S3_ENDPOINT_URL`；`build_services` 建立的儲存為 `S3Storage`。

## 驗收對應

| AC | 場景 |
|---|---|
| AC-001 | S09-01 |
| AC-002 | S09-02 |
| AC-003 | S09-03 |
| AC-004 | S09-03 |
| AC-005 | S09-03 |
| AC-006 | S09-04 |
| AC-007 | S09-02 |

AC-004、AC-005、AC-007 以單元測試驗證（見 design.md）。

## 非功能需求

- S3 金鑰只從環境變數讀取；日誌與錯誤訊息不含金鑰或預簽名網址的簽章。
- 測試用 MinIO 帳密只存在 `infra/docker-compose.test.yml` 與預設的本機設定。
- `Storage` 介面維持 async；S3 用戶端的同步呼叫在執行緒中執行，不阻塞事件迴圈。

## 假設、風險與待決事項

1. **MinIO 映像（需要決定）。** S05 時 `minio/minio`、`quay.io/minio/minio` 都拉不到；2026-10-01 重新確認，以下兩個仍是 MinIO，可以拉取，不偏離架構書，不需要 CR：
   - (A，建議) `bitnamilegacy/minio:2025.5.24`：可固定版本、映像內有 `curl`，compose 可做健康檢查（實測 2 秒內就緒）；缺點是 Bitnami 已停止更新（僅供本機測試，影響有限）。
   - (B) `cgr.dev/chainguard/minio:latest`：持續更新（實測為 2026-09-22 版本），但免費版只有 `latest` 標籤、映像內沒有 shell 與 curl，無法做 compose 健康檢查，測試需自行輪詢就緒。
2. **S3 用戶端用 boto3。** 依開發計畫採用 boto3，同步呼叫以 `asyncio.to_thread` 執行；不使用 aioboto3，以減少依賴。
3. **既有程式改用 `keys.py`。** 開發計畫要求「其他地方不可自行拼接路徑」，因此修改 S06 的 `result_key` 與 S07 的成品路徑，行為與路徑不變（S06、S07 的測試照常通過）。
4. **實景照路徑固定為 `.jpg`。** 依架構書 §7 `projects/{project_id}/scenes/{photo_id}.jpg`；實際格式由 content type 記錄。若之後需要保留原始副檔名，以新的路徑函式處理。
5. **瀏覽器可連到的位址。** 在 docker 中 Worker 以 `http://minio:9000` 連線，瀏覽器需要 `http://localhost:…`；新增 `S3_PUBLIC_ENDPOINT_URL`，只用於產生預簽名網址。
6. **S3 設定不列入正式模式的必要設定。** 與 S05 的 `DATABASE_URL` 相同，加入會改變 S01 已實作的 R-003，需要 CR；缺少時在第一次存取儲存時失敗。
