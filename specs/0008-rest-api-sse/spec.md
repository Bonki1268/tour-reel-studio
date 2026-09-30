# REST API 與 SSE

狀態：approved
版本：v1
關聯開發步驟：S08
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

S07 的快速流程只能在程式內呼叫。前端（S15、S16）需要以 HTTP 操作影片、即時看到進度，而且耗時的企劃與生成必須在背景 Worker 執行，API 立即回應。業者重複點擊「確認」不能造成重複扣點，在錯誤的時機操作要得到明確的拒絕，而不是資料錯亂。

本步驟以 FastAPI 實作架構書 §8 中影片流程所需的端點、SSE 進度串流，以及 API 與 Worker 之間的工作佇列。

## 範圍內／範圍外

**範圍內**
- 端點：`GET /projects/{id}`、`POST /projects/{id}/videos`、`GET /videos/{id}`、`GET /videos/{id}/events`（SSE）、`POST /videos/{id}/plans/regenerate`、`POST /videos/{id}/approve-plan`、`POST /videos/{id}/shots/{no}/regenerate`、`POST /videos/{id}/approve`、`GET /videos/{id}/download`
- 錯誤對應：狀態不符 → 409、驗證錯誤 → 422、找不到 → 404
- `approve-plan` 的 `Idempotency-Key`：同鍵同內容回傳相同回應，同鍵不同內容 → 422
- 工作佇列：`JobQueue` 介面、測試用記憶體佇列、arq（Redis）實作與 Worker 進入點
- 進度事件：Redis pub/sub 版 `EventPublisher` 與訂閱；SSE 端點
- 預簽名下載網址（有效期 ≤ 15 分鐘）：`Storage.presign_get` 介面與記憶體實作（見待決事項 3）
- S07 編排補充：`create_video`（只建立並進入 `planning`）與 `propose_plans`（Worker 執行）分開；新增 `regenerate_plans`

**範圍外**
- `PATCH /projects/{id}/brand-profile`、`POST /projects/{id}/scene-photos`（品牌與實景照管理，S17 以種子腳本建立）
- `POST /webhooks/higgsfield`（S12）
- S3 實作的預簽名網址（S09）；登入與權限（MVP 單一 Demo 帳號）
- Worker 重啟後恢復輪詢、保底成品（S18）

## 使用者旅程

1. 前端送出主題 → 立即得到影片 ID（狀態 `planning`），並訂閱 SSE。
2. 企劃完成時 SSE 推送 `plan_ready`；前端以 `GET /videos/{id}` 取得企劃、鏡頭、成本估算。
3. 業者確認企劃與成本上限 → `approve-plan` 回應 202；重複點擊不會重複生成或扣點。
4. 生成、合成過程以 SSE 推送；`review` 時 `GET /videos/{id}` 提供成品預覽網址。
5. 業者確認成品 → 以短期下載網址下載 MP4。
6. 在錯誤的時機操作（例如生成中要求重新產生企劃）→ 409 與說明訊息。

## 需求

- R-001：`POST /projects/{id}/videos` 以主題建立快速模式影片，回應 201 與影片（狀態 `planning`），並把企劃產生排入 Worker；專案不存在 → 404，主題空白或超過 200 字 → 422。
- R-002：`GET /videos/{id}` 回傳 `status`、`plans`（含每個企劃的成本估算）、`shots`（每鏡的目前版本與結果狀態）、`cost_cap`、`spent`（成本帳加總）；有成品時另含 `preview_url`（短期預簽名網址）。`GET /projects/{id}` 回傳專案、品牌檔案、鎖定角色與實景照。
- R-003：`POST /videos/{id}/approve-plan`（body：`plan_id`、`cost_cap`、可選的每鏡 `placement`）核准企劃並把生成排入 Worker，回應 202；缺少或不合法的欄位 → 422；`cost_cap` 低於該企劃的預估成本 → 422。
- R-004：`approve-plan` 必須帶 `Idempotency-Key` 標頭；同鍵、同內容的重送回傳與第一次相同的狀態碼與內容，不再核准、不再排入工作；同鍵但內容不同 → 422；缺少標頭 → 422。
- R-005：狀態不允許的操作（例如 `generating` 時重新產生企劃、非 `review` 時重生單鏡或確認成品）回應 409；核准失效與超出預算也回應 409，並在內容中標示原因（`approval_invalidated`、`budget_exceeded`，後者含 `requires_reconfirmation: true`）。
- R-006：`GET /videos/{id}/events` 以 SSE 推送該影片的進度事件（`event:` 為事件類型，`data:` 為 JSON，含 `video_id`、`shot_no`、`at`）；連線後先推送一個 `status` 事件（目前狀態），之後推送 S07 發布的每個事件。
- R-007：`GET /videos/{id}/download` 在影片 `approved` 時回傳最新成品的預簽名下載網址與到期時間，有效期不超過 15 分鐘；其他狀態 → 409。
- R-008：`POST /videos/{id}/plans/regenerate`、`POST /videos/{id}/shots/{no}/regenerate` 把工作排入 Worker 並回應 202；`POST /videos/{id}/approve` 確認成品並回應 200。
- R-009：Worker 以 arq 從 Redis 取出工作並執行 S07 編排；API 與 Worker 之間的事件經 Redis pub/sub 傳遞。

## 驗收條件

- AC-001（對應 R-001）：Given 含品牌檔案、1 個已鎖定角色與 3 張實景照的專案，When 以主題「清晨採梅體驗」呼叫 `POST /projects/{id}/videos`，Then 回應 201，內容中影片狀態為 `planning`，且佇列中有 1 個企劃產生工作。
- AC-002（對應 R-001）：不存在的專案 → 404；主題為空白或超過 200 字 → 422，且沒有建立影片。
- AC-003（對應 R-003、R-004）：Given 影片狀態為 `plan_ready`，When 以相同 `Idempotency-Key` 與相同內容呼叫 `approve-plan` 兩次，Then 兩次都回應 202 且內容相同，只有 1 筆企劃核准紀錄、1 組鏡頭（3 個）與佇列中 1 個生成工作。
- AC-004（對應 R-004）：同一個 `Idempotency-Key` 第二次送出不同的 `cost_cap` → 422；沒有 `Idempotency-Key` → 422。
- AC-005（對應 R-003）：Given 影片狀態為 `plan_ready`，When 呼叫 `approve-plan` 但沒有提供 `cost_cap`，Then 回應 422，影片仍為 `plan_ready`；`cost_cap` 小於預估成本、擺放值超出 0～1 → 422。
- AC-006（對應 R-005）：Given 影片狀態為 `generating`，When 呼叫 `POST /videos/{id}/plans/regenerate`，Then 回應 409，影片狀態不變。
- AC-007（對應 R-005）：`InvalidTransition` → 409（`code: invalid_state`）、`ApprovalInvalidated` → 409（`code: approval_invalidated`）、`BudgetExceeded` → 409（`code: budget_exceeded`、`requires_reconfirmation: true`）；不存在的影片 → 404。
- AC-008（對應 R-006）：Given 已訂閱 `GET /videos/{id}/events`，When Worker 完成企劃使影片變為 `plan_ready`，Then 依序收到 `status`（`planning`）與 `plan_ready` 事件，每個 `data` 可解析為 JSON 且含 `video_id`。
- AC-009（對應 R-006）：SSE 格式：每個事件為 `event: <type>`、`data: <JSON>`，以空行結束。
- AC-010（對應 R-007）：Given 影片狀態為 `approved`，When 呼叫 `GET /videos/{id}/download`，Then 回應含 `url` 與 `expires_at`，`expires_at` 距現在不超過 15 分鐘，且網址指向最新成品；`review` 時 → 409。
- AC-011（對應 R-002）：Given 影片狀態為 `review`，When 呼叫 `GET /videos/{id}`，Then 回應包含 `status`、`plans`、`shots`、`cost_cap` 與 `spent`，`spent` 等於成本帳加總，`shots` 有 3 個且各有關鍵幀與影片路徑，並含 `preview_url`。
- AC-012（對應 R-008）：`shots/{no}/regenerate` 在 `review` 時回應 202 並排入 1 個重生工作；`approve` 在 `review` 時回應 200 且影片變為 `approved`。
- AC-013（對應 R-009）：以 arq 將企劃工作排入 Redis，Worker 執行後影片為 `plan_ready`；以 Redis 版事件發布的事件可被另一個連線訂閱收到（`@integration`）。

## 驗收對應

| AC | 場景 |
|---|---|
| AC-001 | S08-01 |
| AC-002 | S08-01 |
| AC-003 | S08-02 |
| AC-004 | S08-02 |
| AC-005 | S08-03 |
| AC-006 | S08-04 |
| AC-007 | S08-04 |
| AC-008 | S08-05 |
| AC-009 | S08-05 |
| AC-010 | S08-06 |
| AC-011 | S08-07 |
| AC-012 | S08-07 |
| AC-013 | S08-05 |

AC-002、AC-004、AC-007、AC-009、AC-012、AC-013 以單元／整合測試驗證（見 design.md）。

## 非功能需求

- 路由只做驗證、冪等與呼叫編排服務；狀態是否合法由領域層判斷。
- API 回應不超過 500 ms（耗時工作一律排入 Worker）；錯誤內容不含堆疊、金鑰或供應商網址。
- 使用者可見的錯誤訊息為繁體中文。

## 假設、風險與待決事項

1. **Worker 佇列（arq）放在 S08。** 開發計畫沒有任何步驟負責 Worker 行程，但 S08 起 API 就必須把工作交給 Worker，S19 也需要真的 Worker。草稿在 S08 建立 `JobQueue` 介面、記憶體佇列（場景測試用，可手動執行排隊的工作）與 arq 實作（`@integration` 測試）。替代方案：S08 只做介面與記憶體佇列，arq 延到 S18。
2. **冪等鍵保存在資料表。** 開發計畫允許 Redis 或資料表。草稿新增 `api_idempotency` 資料表（鍵、端點、影片、請求內容雜湊、狀態碼、回應內容），隨資料庫交易保存，Redis 重啟不會遺失；需要遷移 `0004`。
3. **預簽名網址的介面提前定義。** S08-06 需要短期下載網址，但 S3 實作在 S09。草稿在 `Storage` 介面新增 `presign_get(key, ttl_s)`，記憶體實作回傳含到期時間的測試網址；S09 以 S3 實作同一方法。有效期設定 `PRESIGN_TTL_S`（預設 900，上限 900）。
4. **S07 編排需要拆開。** S07 的 `submit_topic` 同時建立影片並產生企劃；API 必須在 `planning` 就回應，因此拆成 `create_video`（API 呼叫）與 `propose_plans`（Worker 執行），`submit_topic` 保留為兩者的組合，S07 的測試不變。
5. **成本上限低於預估時拒絕（422）。** 架構書只說使用者確認上限；草稿認為低於預估的上限必然在生成中途卡住，因此在 API 就拒絕。若你希望允許（只在送出時由預算檢查阻擋），請告訴我。
6. **`review` 時的預覽。** 下載端點只在 `approved` 時提供（架構書「成品確認 → 下載」）；成品確認頁需要播放影片，因此 `GET /videos/{id}` 在有成品時附上 `preview_url`。
7. **SSE 測試方式。** httpx 的 ASGI 測試傳輸不支援持續串流，S08-05 在測試中以 uvicorn 啟動真的伺服器（隨機埠）並用 httpx 串流讀取；事件來源使用記憶體版事件匯流排。Redis 版事件另以 `@integration` 測試驗證。
8. **不做斷線重送（`Last-Event-ID`）。** 重新連線時先收到 `status` 事件即可同步目前狀態，前端再以 `GET /videos/{id}` 取得完整資料。
