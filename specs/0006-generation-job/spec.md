# 生成工作與重試

狀態：approved
版本：v1
關聯開發步驟：S06
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

每一鏡的關鍵幀與影片都要呼叫外部供應商（Higgsfield），這些呼叫要花錢、耗時數分鐘，而且可能失敗、逾時或重複送出。業者需要的保證是：失敗會自動補救一次、補救不了就明確停下來讓人處理、不會因為重送或 Worker 重啟而重複扣點，也不會在核准失效或超出預算時偷偷花錢。

本步驟實作架構書 §6.2 的生成工作流程：`run_generation_job` 依序執行「核准檢查 → 預算檢查 → 送出 → 等待 → 轉存 → 記帳」，以 `FakeProvider` 與記憶體儲存驗證，真實 Higgsfield 串接留到 S12。

## 範圍內／範圍外

**範圍內**
- 供應商介面（架構書 §5.5）：`ImageProvider.compose`、`VideoProvider.image_to_video`、查詢結果、下載結果；`ProviderJob`、`ProviderResult`、`ProviderError`（可否重試）
- `FakeProvider`：可設定成功、第 N 次失敗、永遠失敗、不可重試的失敗、永不完成、耗時、回報的實際成本
- 生成工作狀態：`queued → submitted → running → succeeded → stored`，`failed`、`failed_final`
- 自動重試一次、逾時、冪等、送出前檢查核准與預算、成功後轉存與記帳
- 最小的物件儲存介面 `Storage`（`put`、`get`、`exists`）與記憶體實作（見待決事項 3）
- 設定：`GENERATION_TIMEOUT_S`（預設 600）、`GENERATION_POLL_INTERVAL_S`（預設 5）
- repository 補充：更新生成工作、更新鏡頭版本的結果路徑

**範圍外**
- 真實 Higgsfield adapter、webhook（S12）
- arq 佇列與 Worker 行程、同一支影片 3 鏡平行與「關鍵幀 → 影片」順序編排（S07）
- S3 相容儲存、預簽網址（S09）
- API 與 SSE 推送工作狀態（S08）

## 使用者旅程

本步驟沒有新的使用者介面。業者可觀察到的結果：

1. 某一鏡生成偶爾失敗時，系統自動再試一次，業者不需要做任何事。
2. 再試一次仍失敗時，影片狀態變成「需要處理」，而不是無限重試、持續扣點。
3. 網路不穩或 Worker 重啟造成同一個工作被執行兩次時，不會重複扣點。
4. 核准後內容被改動，或花費會超出核准的上限時，系統不會送出請求，而是要求重新確認。

## 需求

- R-001：生成工作成功時，狀態依序經過 `queued`、`submitted`、`running`、`succeeded`、`stored`；結果下載後存入自有物件儲存（路徑依架構書 §7），鏡頭版本記錄自有路徑，工作記錄供應商的 request ID（`external_id`）。
- R-002：一次嘗試失敗（供應商回報失敗、可重試的錯誤或逾時）時自動重試一次；重試是新的嘗試（`attempt` 加 1，新的 `provider_idempotency_key`），不需要再次核准，但仍需通過預算檢查；每個工作最多送出 2 次。
- R-003：重試後仍失敗時，工作狀態為 `failed_final`，所屬影片由 `generating` 變為 `needs_attention`；供應商回報不可重試的錯誤時不重試，直接 `failed_final`。
- R-004：嘗試自進入 `submitted` 起超過設定的逾時秒數仍未完成時視為失敗（錯誤標示為逾時），並依 R-002 重試；逾時秒數與輪詢間隔由設定決定。
- R-005：以相同冪等鍵再次執行時不重複呼叫供應商、不重複扣點：已 `stored` 的工作直接回傳；已送出但未完成的工作以既有 `external_id` 繼續查詢，不重新送出。冪等鍵的其他組成相同但輸入雜湊不同時，視為新的工作。
- R-006：每次送出（含重試）前檢查核准仍有效；輸入在核准後被修改時不呼叫供應商，影片退回 `plan_ready`。
- R-007：每次送出（含重試）前檢查預算；超出核准上限時不呼叫供應商並要求重新確認。成功後以實際成本（未回報時用單價表）在成本帳新增一筆，同一工作只記一次；失敗的嘗試釋放其預留額度。
- R-008：工作每次狀態變更都寫入 repository（含 `external_id`、`provider_idempotency_key`、`attempt`、錯誤），Worker 重啟後可依紀錄繼續。

## 驗收條件

- AC-001（對應 R-001）：Given FakeProvider 設定為成功，When 執行一個關鍵幀生成工作，Then 工作狀態依序為 `queued`、`submitted`、`running`、`succeeded`、`stored`；物件儲存中存在 `videos/{video_id}/shots/{shot_no}/take{n}/keyframe.png` 且內容為供應商回傳的結果；鏡頭版本的 `keyframe_key` 為該路徑；工作的 `external_id` 為 FakeProvider 回傳的 request ID。
- AC-002（對應 R-002）：Given FakeProvider 設定為第 1 次失敗、第 2 次成功，When 執行一個影片生成工作，Then 最後一次嘗試狀態為 `stored`、`attempt` 為 2，供應商共收到 2 次送出，兩次的 `provider_idempotency_key` 不同。
- AC-003（對應 R-003）：Given FakeProvider 設定為永遠失敗，When 執行一個影片生成工作，Then 最後一次嘗試狀態為 `failed_final`，供應商共收到 2 次送出，影片狀態由 `generating` 變為 `needs_attention`，成本帳沒有新增紀錄。
- AC-004（對應 R-003）：Given FakeProvider 第 1 次回報不可重試的錯誤，When 執行工作，Then 供應商只收到 1 次送出，工作 `failed_final`，影片 `needs_attention`。
- AC-005（對應 R-004）：Given FakeProvider 設定為永不完成且逾時為 1 秒，When 執行一個影片生成工作，Then 第 1 次嘗試在進入 `submitted` 後 1 秒被判定為逾時失敗、錯誤標示為逾時，並送出第 2 次嘗試；排隊等待的時間不計入逾時（以可注入的時鐘驗證，不實際等待）。
- AC-006（對應 R-005）：Given 一個已 `stored` 並已記帳的工作，When 以相同冪等鍵再次執行，Then 供應商沒有收到任何呼叫，成本帳筆數不變，回傳的工作與原本相同。
- AC-007（對應 R-005）：Given 一個已送出（有 `external_id`）但尚未完成的工作，When 以相同冪等鍵再次執行，Then 供應商沒有收到新的送出，而是以既有 `external_id` 查詢並完成；Given 冪等鍵其他組成相同但輸入雜湊不同，Then 建立新的工作並送出。
- AC-008（對應 R-006）：Given 企劃已核准但第 1 鏡的輸入在核准後被修改，When 執行第 1 鏡的關鍵幀生成工作，Then 供應商沒有收到任何呼叫，影片退回 `plan_ready`，呼叫端收到 `ApprovalInvalidated`。
- AC-009（對應 R-007）：Given 已花費加上此工作預估會超出上限，When 執行工作，Then 供應商沒有收到任何呼叫，呼叫端收到 `BudgetExceeded`（`requires_reconfirmation` 為真）；Given 第 1 次嘗試失敗且重試會超出上限，Then 不送出重試。
- AC-010（對應 R-007）：Given FakeProvider 成功並回報實際成本 1.8 點，When 執行工作，Then 成本帳新增恰好 1 筆 1.8 點（`source=provider`）；未回報實際成本時以單價表記帳（`source=table`）；失敗的嘗試不留下預留額度。
- AC-011（對應 R-008）：生成工作的更新（狀態、`external_id`、`provider_idempotency_key`、`attempt`、錯誤、實際成本）與鏡頭版本結果路徑的更新，在記憶體版與資料庫版 repository 讀回結果一致。

## 驗收對應

| AC | 場景 |
|---|---|
| AC-001 | S06-01 |
| AC-002 | S06-02 |
| AC-003 | S06-03 |
| AC-004 | S06-03 |
| AC-005 | S06-04 |
| AC-006 | S06-05 |
| AC-007 | S06-05 |
| AC-008 | S06-06 |
| AC-009 | S06-06 |
| AC-010 | S06-01 |
| AC-011 | S06-01 |

AC-004、AC-007、AC-009、AC-010、AC-011 的細節以單元測試驗證（見 design.md）。

## 非功能需求

- 測試不實際等待：逾時與輪詢使用可注入的時鐘與 `sleep`，S06 全部測試在數秒內完成。
- 領域規則（狀態轉換、重試判斷、逾時判斷）放在 `app/domain/`，不依賴供應商或資料庫。
- 模型名稱只從設定讀取；日誌與錯誤訊息不包含 API 金鑰或結果網址中的簽章參數。
- 點數一律使用 `Decimal`。

## 假設、風險與待決事項

**使用者決定（2026-10-01）：以下 1～8 項全部採用草稿建議。**

1. **重試是「同一筆工作」還是「新的一筆工作」（需要決定）。** 架構書 §6.2 的圖把重試畫成 `failed → submitted`，但同一節又說「新的自動重試才建立新的 attempt 與新的 key」，而 S05 的冪等鍵包含 `attempt` 且有唯一索引。草稿採用：**每次嘗試是一筆 `generation_jobs` 紀錄**（第 2 次嘗試 `attempt=2`，冪等鍵與 `provider_idempotency_key` 都是新的），因此每次送出的 `external_id` 與錯誤都能追溯。§6.2 圖中的 `failed → submitted` 解讀為「前一筆 failed 後，新一筆從 queued 進入 submitted」。場景中的「工作」指同一鏡、同一種類的整組嘗試。
2. **冪等鍵中的 `attempt` 與鏡頭版本的 `attempt`。** 草稿中冪等鍵的 `attempt` 是工作的嘗試次數（1 或 2）；使用者重生鏡頭會建立新的鏡頭版本（S05），其工作的冪等鍵以新版本的 `shot_take_id` 區分——但 S05 的冪等鍵格式 `video:shot:kind:hash:attempt` 不含鏡頭版本。**同一鏡重生且輸入完全相同時，冪等鍵會與前一版本相同，重生會被當成重複請求。** 草稿建議：`input_hash` 納入鏡頭版本的 attempt（或 seed），使重生時雜湊不同；不改 S05 的格式。若你希望改成在冪等鍵中明確加入鏡頭版本，需要另開 CR 修改 S05。
3. **物件儲存介面提前在 S06 定義最小版本。** 場景 S06-01 要求「結果已存入物件儲存」，但 `Storage` 依開發計畫在 S09 建立。草稿在 S06 定義 `Storage` Protocol 的最小子集（`put`、`get`、`exists`）與記憶體實作，S09 再補上預簽網址與 S3 實作，不改動已定義的方法。
4. **核准失效時工作的狀態。** §6.2 沒有定義。草稿：工作維持 `queued`、`error` 記錄 `approval_invalidated`，不進入 `failed_final`（避免把影片推到 `needs_attention`，與「退回 `plan_ready`」衝突）；超出預算時同樣維持 `queued`、`error` 記錄 `budget_exceeded`。重新核准後由 S07 決定是否重送。
5. **S04 的 `Budget` 需要新增 `release(job_id)`。** 失敗的嘗試要釋放預留額度（R-007），S04 目前沒有此方法。這是新增方法、不改變既有行為與測試，草稿視為本步驟範圍內；若你認為需要 CR，請告訴我。
6. **S05 的 repository 介面需要新增方法**：`GenerationJobRepository.update(job)`、`get_by_key(key)`，`ShotRepository.update_take(take)`。同樣是新增、不改既有行為，記憶體版與資料庫版都要實作並以參數化測試驗證（AC-011）。
7. **逾時的定義。** 依開發計畫「逾時計時從 `submitted` 開始」；每次嘗試各自計時，重試的逾時重新計算。
8. **逾時後是否向供應商取消請求。** 架構書沒有說明，Higgsfield 是否支援取消待 S12 確認。草稿不取消，只停止等待；已逾時的請求若之後仍扣點，會在 S12 以實際帳單對帳時處理。
