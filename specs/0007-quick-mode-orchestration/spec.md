# 快速模式工作編排

狀態：approved
版本：v1
關聯開發步驟：S07
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

S02～S06 各自完成了狀態機、核准、成本、持久化與單一生成工作，但業者要的是一條完整流程：輸入一句主題，挑一個企劃並確認成本，之後系統自己把 3 鏡做完、合成成品，業者只在「企劃確認」與「成品確認」兩個地方做決定（架構書 §5.2）。

本步驟以假的創作引擎、供應商、合成器與記憶體儲存，把「主題 → 企劃 → 3 鏡平行生成 → 合成 → 成品確認」串成 `QuickModeOrchestrator`，並在每個階段發布進度事件。真實的 Claude（S10）、Higgsfield（S12）、FFmpeg（S13）之後替換介面實作即可。

## 範圍內／範圍外

**範圍內**
- `CreativeEngine` 介面（架構書 §5.4）與 `FakeCreativeEngine`（回傳固定的 2～3 個企劃）
- `Renderer` 介面與 `FakeRenderer`（產生時間軸 JSON 與空白成品檔）
- 進度事件：`ProgressEvent`、`EventPublisher` 介面、記憶體版 `MemoryEventBus`
- `QuickModeOrchestrator`：送出主題、列出企劃、估算成本、核准企劃、生成（3 鏡平行，每鏡關鍵幀 → 影片依序）、合成、成品核准、成品確認時重生單鏡
- 快速模式自動採用的階段寫入 `auto_approved=true` 的核准紀錄
- repository 補充（S05 標為「用到時再加入」者）：企劃、角色與角色版本、實景照、成品（renders）
- `FakeProvider` 補充：每個工作耗時、依鏡頭編號設定結果

**範圍外**
- HTTP API 與 SSE、Redis 版事件發布、arq 佇列（S08）
- 真實企劃產生（S10）、B1 照片合成的粗合成圖（S11）、Higgsfield（S12）、FFmpeg 與片尾卡（S13、S14）
- 進階模式、多比例與多語成品

## 使用者旅程

1. 業者輸入主題「清晨採梅體驗」→ 看到 2～3 個企劃與成本估算。
2. 選第 1 個企劃（可調整每鏡角色位置）並確認成本上限 → 系統開始生成，畫面陸續顯示每鏡開始與完成。
3. 3 鏡完成後系統自動合成，狀態變成「待確認」。
4. 業者滿意就確認成品；不滿意某一鏡可單獨重生，其他鏡保持不變，重生後重新合成並回到「待確認」。
5. 若某一鏡重試後仍失敗，其他鏡的成果保留，影片變成「需要處理」。

## 需求

- R-001：送出主題後，影片依序進入 `planning`、`plan_ready`，並保存創作引擎提出的 2～3 個企劃；創作引擎失敗或回傳的企劃數不在 2～3 之間時，影片進入 `failed`。
- R-002：使用者選擇一個企劃、（可選）調整每鏡擺放並以成本上限核准後，系統依企劃建立 3 個鏡頭與各自的第 1 個版本，影片進入 `generating`，並寫入 1 筆使用者核准（`plan`）紀錄。
- R-003：生成時 3 鏡平行執行，每鏡內先關鍵幀、後影片；全部完成後影片進入 `rendering`，合成產生時間軸 JSON 與成品檔，影片進入 `review`。
- R-004：每個階段發布進度事件，事件包含 `type`、`video_id`、`shot_no`（鏡頭相關事件）與 `at`；事件類型至少有 `plan_ready`、`shot_started`、`shot_done`、`shot_failed`、`render_started`、`review_ready`、`needs_attention`。
- R-005：某一鏡重試後仍失敗時，其他鏡頭照常完成且結果保留；影片進入 `needs_attention`，不進行合成。多鏡同時失敗時影片同樣只進入一次 `needs_attention`。
- R-006：影片在 `review` 時使用者可重生單一鏡頭：只有該鏡新增版本並重新生成，其他鏡頭的目前版本不變；完成後重新合成，影片回到 `review`。
- R-007：整個快速流程中，使用者親自確認的核准只有 `plan` 與 `final` 兩筆；系統自動採用的階段（腳本、素材、每鏡關鍵幀）以 `auto_approved=true` 記錄。
- R-008：企劃、角色版本、實景照與成品紀錄可寫入並讀回，記憶體版與資料庫版 repository 行為一致。

## 驗收條件

- AC-001（對應 R-001）：Given 含品牌檔案、1 個已鎖定角色與 3 張實景照的專案，When 使用者送出主題「清晨採梅體驗」，Then 影片狀態歷程為 `draft → planning → plan_ready`，保存 2～3 個企劃，且創作引擎收到的 PlanContext 含品牌檔案、主題、角色錨點卡與 3 張實景照。
- AC-002（對應 R-001）：Given FakeCreativeEngine 拋出錯誤或只回傳 1 個企劃，When 送出主題，Then 影片狀態為 `failed`。
- AC-003（對應 R-002、R-003）：When 使用者選擇第 1 個企劃並以預估上限核准、系統開始生成，Then 3 個鏡頭各自有關鍵幀與影片（鏡頭版本的 `keyframe_key`、`clip_key` 皆存在於物件儲存），影片狀態依序經過 `generating`、`rendering`、`review`，影片的時間軸 JSON 已保存，物件儲存中有 1 個成品檔且有 1 筆成品紀錄。
- AC-004（對應 R-003）：Given FakeProvider 每個工作耗時 1 秒，When 核准企劃後開始生成，Then 所有鏡頭在 3 秒內完成（循序執行需 6 秒）。
- AC-005（對應 R-004）：When 完成一次完整快速流程，Then 進度事件依序包含 `plan_ready`、`shot_started`、`shot_done`、`render_started`、`review_ready`（依序指子序列），且每個事件都帶有 `video_id` 與 `at`，鏡頭相關事件帶有 `shot_no`。
- AC-006（對應 R-005）：Given FakeProvider 對第 2 鏡永遠失敗，When 核准企劃後開始生成，Then 第 1 鏡與第 3 鏡的關鍵幀與影片都已保存，影片狀態為 `needs_attention`，發布 `shot_failed`（shot_no=2）與 `needs_attention` 事件，沒有 `render_started` 事件。
- AC-007（對應 R-005）：Given FakeProvider 對第 1 與第 2 鏡都永遠失敗，When 開始生成，Then 不拋出例外，影片狀態為 `needs_attention`，狀態歷程中只有一次進入 `needs_attention`。
- AC-008（對應 R-006）：Given 一支狀態為 `review` 的影片，When 使用者重生第 3 鏡，Then 第 3 鏡有 2 個版本且目前版本為第 2 版，第 1、2 鏡的目前版本不變且供應商沒有收到它們的新請求，成品重新合成（成品紀錄變為 2 筆），影片狀態歷程最後為 `review → generating → rendering → review`。
- AC-009（對應 R-007）：When 完成一次完整快速流程（含成品核准），Then `auto_approved=false` 的核准紀錄恰好 2 筆，類型為 `plan` 與 `final`；其餘核准紀錄（`script`、`assets`、每鏡 `keyframes`）的 `auto_approved` 皆為 true。
- AC-010（對應 R-008）：企劃、角色與角色版本、實景照、成品的新增與讀回，在記憶體版與資料庫版 repository 結果一致。

## 驗收對應

| AC | 場景 |
|---|---|
| AC-001 | S07-01 |
| AC-002 | S07-01 |
| AC-003 | S07-01 |
| AC-004 | S07-02 |
| AC-005 | S07-03 |
| AC-006 | S07-04 |
| AC-007 | S07-04 |
| AC-008 | S07-05 |
| AC-009 | S07-06 |
| AC-010 | S07-01 |

AC-002、AC-007、AC-010 以單元測試驗證（見 design.md）。

## 非功能需求

- 領域規則（狀態轉換、核准、預算）仍只在 `app/domain/`；編排層不自行判斷狀態是否合法。
- 除 AC-004 外，測試不實際等待；AC-004 以真實時間驗證平行度，單一測試不超過 3 秒。
- 模型名稱只從設定讀取；企劃與事件內容不含 API 金鑰。

## 假設、風險與待決事項

1. **S06 需要一個小修正。** 目前 `run_generation_job` 在一鏡最終失敗時直接對影片套用 `SHOT_FAILED_FINAL`；兩鏡同時失敗時，第二次套用會因影片已在 `needs_attention` 而拋出 `InvalidTransition`。草稿改為只有影片仍在 `generating` 時才套用（AC-007），不改變 S06 已驗收的單鏡行為。
2. **自動核准的粒度。** 草稿：`script`（依企劃產生的每鏡提示詞）與 `assets`（使用的角色版本與實景照）各 1 筆，`keyframes` 每鏡 1 筆（關鍵幀完成、送出圖生影片前）。
3. **核准後才開始生成，兩者分開呼叫。** `approve_plan` 只做核准與建立鏡頭；`generate` 是 Worker 任務（S08 由 API 排入佇列）。場景中的「核准企劃後開始生成」依序呼叫兩者。
4. **新增 4 個 repository。** S05 把企劃、角色、實景照、成品的 repository 留到「用到時再加入」；S07 的流程需要讀取角色與實景照、保存企劃與成品，因此在本步驟加入（資料表已存在，不需要遷移）。
5. **合成器介面。** 草稿：`Renderer.build_timeline(video, shots)` 產生時間軸 JSON；`Renderer.render(timeline, storage, output_key)` 產生成品檔。S13 以 FFmpeg 實作同一介面，時間軸結構屆時由 S13 規格定義，S07 只要求它是可保存的 JSON。
6. **重生單鏡的預算。** 重生沿用原本的企劃核准與成本上限（上限已預留一鏡完整重生）；超出上限時由 S06 的預算檢查拋出 `BudgetExceeded`，影片停在 `generating`，由呼叫端（S08）詢問使用者。
7. **成本估算。** 核准前的估算使用 S04 `estimate_video`（鏡數依所選企劃、模型依設定）；「以預估上限核准」即以其 `cap` 核准。
