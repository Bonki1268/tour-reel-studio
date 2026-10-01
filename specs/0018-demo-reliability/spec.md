# Demo 可靠性

狀態：approved
版本：v1
關聯開發步驟：S18
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

Demo 現場網路不可控（架構書 §2.2、§9.3）：Higgsfield 的 webhook 可能進不來、可能重複送達，Worker 可能被重啟，生成也可能比預期久。目前的實作以輪詢為唯一結果來源（S12），webhook 只回 202；但工作的狀態寫入是「讀出 → 修改 → 整筆覆寫」，當 webhook 觸發的處理、輪詢、或重啟後重複執行的 Worker 同時看到同一個成功結果時，結果會被轉存多次、成本帳可能重複。Worker 啟動時也不會接續已送出的工作，影片會停在 `generating`。

本步驟目標：
1. 沒有 webhook（關閉或遺失）時以輪詢完成。
2. webhook 收到後立即查詢並轉存，不必等下一次輪詢；任何來源同時回報時只處理一次。
3. Worker 重啟後接續進行中的工作，不重新送出（不重複計費）。
4. 生成超過展示門檻時，API 提供事先準備的保底成品網址，背景生成照常進行。

## 範圍內／範圍外

**範圍內**
- 生成工作狀態的條件更新（只有在資料庫中的狀態仍是預期值時才寫入），記憶體與 SQL repository 都實作
- 結果處理（下載 → 轉存 → 更新鏡頭版本 → `stored` → 記帳）抽成輪詢與 webhook 共用的函式，以「`submitted`／`running` → `succeeded`」的條件更新取得處理權
- `POST /webhooks/higgsfield`：簽章有效時找出對應工作，排入 Worker 工作 `process_webhook`；Worker 向 Higgsfield 查詢狀態（不採用通知內容），成功時走共用的結果處理
- Worker 啟動時的恢復掃描（arq `on_startup`）
- 保底成品：設定 `DEMO_FALLBACK_VIDEO`（自有儲存中的物件路徑）與 `DEMO_FALLBACK_AFTER_S`；`GET /videos/{id}` 多回傳 `fallback_url`

**範圍外**
- 前端顯示保底成品（見待決事項 1）
- 合成（rendering）中斷後的恢復：合成約 30 秒，Worker 重啟時影片停在 `rendering`，由使用者重新觸發（S19 之後再評估）
- 多個 Worker 同時執行同一影片時的事件去重（SSE 可能收到重複的 `shot_done`；前端以最新狀態為準）
- 保底成品的上傳方式（手動放入儲存，見待決事項 3）

## 使用者旅程

1. Demo 現場關閉 webhook（`WEBHOOK_ENABLED=false`）或 webhook 進不來；業者確認企劃後，進度頁照常更新，影片以輪詢完成。
2. webhook 正常時，Higgsfield 完成通知一到，該鏡立即轉存並推進，不用等下一次輪詢；重複通知不影響結果與成本。
3. Worker 當機重啟後，進行中的鏡頭接續查詢原本的生成請求，完成後影片照常進入成品確認。
4. 生成比預期久、超過展示門檻時，前端可取得保底成品網址先播放，並說明生成仍在背景進行；完成後改看真正的成品。

## 需求

- R-001：`WEBHOOK_ENABLED=false` 時，送給 Higgsfield 的請求不帶回呼網址；影片生成工作以輪詢查到完成，結果轉存到自有儲存、成本帳記一筆，工作狀態為 `stored`。
- R-002：webhook 已啟用且請求帶有回呼網址，但通知始終未送達時，工作仍以輪詢完成，結果與 R-001 相同。
- R-003：簽章有效的 webhook 會讓系統立即向 Higgsfield 查詢該工作的狀態（不採用通知內容），查到成功時馬上轉存，不等下一次輪詢；簽章無效回 401（S12 不變）；找不到對應工作或工作已結束時回 202 且不做任何變更。
- R-004：同一個工作的成功結果無論由幾個來源同時回報（webhook、輪詢、重啟後重複執行的 Worker），結果只下載與轉存一次、鏡頭版本只更新一次、成本帳只記一筆，工作最後為 `stored`；沒有取得處理權的來源視同完成並讓影片照常推進。
- R-005：Worker 啟動時接續進行中的工作：狀態為 `submitted`／`running` 且未逾時的工作，以原本的外部 request ID 繼續輪詢直到完成（不重新送出、不重複計費），所屬影片照常推進；已逾時的工作標記為失敗（`timeout`），依 S06 規則自動重試一次；停在 `succeeded`（轉存途中中斷）的工作標記為失敗（`interrupted`），同樣依規則重試。
- R-006：設定 `DEMO_FALLBACK_VIDEO` 且該物件存在時，影片進入 `generating` 後超過 `DEMO_FALLBACK_AFTER_S` 秒、狀態仍為 `generating`／`rendering`／`needs_attention` 且還沒有成品，`GET /videos/{id}` 回傳 `fallback_url`（預簽名網址）；其他情況為 `null`。查詢沒有副作用，背景生成照常進行，完成後 `preview_url` 出現、`fallback_url` 變回 `null`。

## 驗收條件

- AC-001（對應 R-001）：Given `WEBHOOK_ENABLED=false`、Higgsfield 以 HTTP mock 回應（先 `in_progress` 再 `completed`），When 執行一個影片生成工作，Then 送出的請求沒有 `hf_webhook` 參數、工作為 `stored`、自有儲存有鏡頭影片、成本帳 1 筆。
- AC-002（對應 R-002）：Given webhook 已啟用（`PUBLIC_BASE_URL`、`HIGGSFIELD_WEBHOOK_SECRET` 已設定）且 webhook 端點從未被呼叫，When 執行一個影片生成工作，Then 送出的請求帶有 `hf_webhook`，工作仍以輪詢完成，結果同 AC-001。
- AC-003（對應 R-003、R-004）：Given 一個 `running` 的工作，Higgsfield 已回報完成，When webhook 觸發的處理與輪詢同時處理該結果，Then 結果物件只寫入一次、成本帳 1 筆、工作為 `stored`，影片只推進一次（該鏡接下來的影片工作只送出一次，影片最後進入 `review`）。
- AC-004（對應 R-005）：Given 一個 `submitted` 的工作（Worker 在送出後中止），When 以相同的資料庫與儲存重新啟動 Worker，Then 該工作以原本的 request ID 查詢並完成（供應商送出次數不變），影片進入 `review`。
- AC-005（對應 R-006）：Given 已設定且已上傳保底成品、生成時間超過展示門檻，When 前端查詢 `GET /videos/{id}`，Then 回應含 `fallback_url`、影片仍為 `generating`；When 背景生成完成，Then 影片進入 `review`、`preview_url` 有值、`fallback_url` 為 `null`。
- AC-006（對應 R-004）：單元測試：記憶體與 SQL repository 的條件更新，兩個同時以相同預期狀態更新同一個工作時只有一個成功；輸者讀回的是贏家寫入的內容。
- AC-007（對應 R-003）：單元測試：簽章有效且對應到工作時排入 `process_webhook`；對應不到工作時回 202 且不排入；簽章無效回 401 且不排入；`process_webhook` 遇到已 `stored` 的工作時不查詢供應商、不寫入。
- AC-008（對應 R-005）：單元測試：恢復掃描只讓未逾時的 `submitted`／`running` 工作接續輪詢；逾時與 `succeeded` 的工作標記為失敗；每部影片只排入一次接續工作；`generating` 以外的影片不排入。
- AC-009（對應 R-006）：單元測試：門檻前、未設定、物件不存在、已有成品、狀態為 `review` 時 `fallback_url` 為 `null`；門檻計算以最後一次進入 `generating` 的時間為準。

## 驗收對應

| AC | 場景 |
|---|---|
| AC-001 | S18-01 |
| AC-002 | S18-02 |
| AC-003 | S18-03 |
| AC-004 | S18-04 |
| AC-005 | S18-05 |
| AC-006 | S18-03 |
| AC-007 | S18-03 |
| AC-008 | S18-04 |
| AC-009 | S18-05 |

S18 場景沒有 `@integration` 標籤：場景以記憶體 repository、`FakeProvider` 或 `HiggsfieldProvider`＋`respx` 執行；SQL 的條件更新以 AC-006 的單元測試在測試資料庫驗證（閘門會啟動 PostgreSQL）。

## 非功能需求

- 條件更新為單一 SQL 敘述（`UPDATE … WHERE id = :id AND status = :expected`），不依賴應用程式鎖，多個 Worker 行程之間也成立。
- webhook 端點在 100 ms 內回應（只驗證、查一次資料庫、排入工作），不在 API 行程中下載結果。
- 保底成品網址與成品網址相同，以預簽名網址提供，有效期 `PRESIGN_TTL_S`。
- 日誌帶 `job_id`；webhook 處理與恢復掃描記錄結果（已處理、已由其他來源完成、略過）。

## 假設、風險與待決事項

1. **前端是否在本步驟顯示保底成品（需要決定）。** S18 的測試套件只有 `py`；只做 API 時，現場要有人手動切換播放保底影片。若要前端在進度頁出現「先看保底成品」，需要像 CR-0001／CR-0002 一樣起草 CR 把 S18 套件加上 `web`（＋`e2e`），並補一個場景。**草稿建議：本步驟只做 API，前端顯示放到 S19 前以 CR 補上。**
2. **展示門檻預設值。** 架構書 §9.4 的關鍵幀＋影片目標約 5.5 分鐘；草稿預設 `DEMO_FALLBACK_AFTER_S=420`（7 分鐘），由 `.env` 調整。
3. **保底成品放到儲存的方式。** `DEMO_FALLBACK_VIDEO` 是自有儲存中的物件路徑（例如 `demo/fallback.mp4`），草稿不提供上傳工具，Demo 前以 MinIO 主控台或 `mc cp` 手動放入（可用預熱時跑出的成品）。若希望由種子腳本上傳，需另起 CR 修改 S17。
4. **`succeeded` 中斷時重新送出。** 停在 `succeeded` 代表轉存途中中斷；草稿標記為失敗並依規則重試（會重新送出、多花一次費用），不新增 `succeeded → running` 的狀態轉換（S06 的轉換表不變）。這種情況只發生在下載／上傳的幾秒內。
5. **webhook 處理在 Worker。** 下載影片可能數十 MB，不在 API 行程中執行；代價是多一次佇列往返（毫秒級）。
6. **保底成品的觸發狀態。** 包含 `needs_attention`（某鏡失敗待處理時現場仍可展示保底）；不含 `plan_ready` 以前與 `review` 以後。
