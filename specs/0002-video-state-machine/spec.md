# 影片狀態機

狀態：approved
版本：v1
關聯開發步驟：S02
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

影片從選題到成品確認會經過企劃、生成、合成、確認等階段，其中生成要花錢。只要有一個流程能讓影片跳過某個階段（例如沒核准企劃就開始生成，或已確認的成品又被重生），就可能產生未經同意的費用或錯亂的成品。

本步驟在 `backend/app/domain/video.py` 實作架構書 §6.1 的影片狀態機，之後的核准（S03）、生成工作（S06）、編排（S07）與 API（S08）都只能透過它改變影片狀態。

## 範圍內／範圍外

**範圍內**
- `VideoStatus`、`VideoEvent` 列舉與以資料表示的轉換表
- `Video.apply(event)`：合法時轉換並記錄歷程，不合法時拋出 `InvalidTransition` 且不改變任何狀態
- 狀態歷程（事件名稱、轉換前後狀態、時間）

**範圍外**
- 持久化與並行更新（S05）
- 合成自動重試「最多 1 次」的次數控制：由工作層（S06／S13）負責，狀態機只提供 `rendering → rendering` 轉換
- 預算不足時的「暫停並詢問」（架構書 §6.4）：§6.1 沒有對應狀態，留待 S04 規格決定
- 觸發轉換的條件本身（例如雜湊比對、所有鏡頭是否完成）：由 S03、S06、S07 判斷後呼叫 `apply`

## 使用者旅程

使用者（觀光業者）看不到狀態機本身，但會觀察到它的結果：

1. 送出主題後看到「企劃產生中」，完成後看到企劃卡；不滿意可重新產生。
2. 核准企劃與成本上限後才開始生成；某鏡重試後仍失敗時，看到「需要處理」並可確認重生。
3. 合成完成後進入成品確認，可以重生單鏡或確認成品；確認後的影片不能再被改動。

## 需求

- R-001：影片只能依下列轉換表改變狀態（架構書 §6.1，事件名稱見 design.md）：

  | 目前狀態 | 事件 | 新狀態 |
  |---|---|---|
  | draft | submit_topic | planning |
  | planning | plans_ready | plan_ready |
  | planning | planning_failed | failed |
  | plan_ready | regenerate_plans | planning |
  | plan_ready | approve_plan | generating |
  | generating | all_shots_done | rendering |
  | generating | shot_failed_final | needs_attention |
  | generating | approval_invalidated | plan_ready |
  | needs_attention | confirm_regenerate | generating |
  | needs_attention | confirm_rerender | rendering |
  | rendering | render_done | review |
  | rendering | render_retry | rendering |
  | rendering | render_failed_final | needs_attention |
  | review | regenerate_shot | generating |
  | review | approve_final | approved |

  其中 `generating --approval_invalidated--> plan_ready` 不在 §6.1 圖中，依 §6.3 與場景 S03-04、S06-06 加入（見待決事項 1）。
- R-002：不在轉換表中的「狀態 × 事件」組合一律被拒絕：拋出狀態轉換錯誤，影片狀態與歷程都不變。
- R-003：`approved` 與 `failed` 是終止狀態，任何事件都被拒絕；其他狀態都至少有一個出口。
- R-004：每次成功的轉換都在影片的狀態歷程中留下一筆紀錄，包含事件名稱、轉換前狀態、轉換後狀態與時間；歷程依發生順序保存。

## 驗收條件

- AC-001（對應 R-001）：Given 一支狀態為轉換表中「目前狀態」的影片，When 發生該列的事件，Then 影片狀態變為該列的「新狀態」；轉換表的 15 列全部成立。
- AC-002（對應 R-002）：Given 一支狀態為 `generating` 的影片，When 發生事件 `approve_plan`，Then 拋出狀態轉換錯誤，影片狀態仍為 `generating`，且歷程沒有新增紀錄。
- AC-003（對應 R-002）：對全部 9 個狀態 × 15 個事件的組合窮舉，不在轉換表中的每一組都拋出狀態轉換錯誤。
- AC-004（對應 R-003）：Given 一支狀態為 `approved` 或 `failed` 的影片，When 發生任何事件（例如 `regenerate_shot`），Then 拋出狀態轉換錯誤；且除這兩者外的每個狀態在轉換表中至少有一個出口。
- AC-005（對應 R-004）：Given 一支狀態為 `draft` 的影片，When 依序發生 `submit_topic` 與 `plans_ready`，Then 狀態歷程依序為 `draft`、`planning`、`plan_ready`，且兩筆轉換紀錄各自帶有事件名稱與時間，時間不早於前一筆。

## 驗收對應

| AC | 場景 |
|---|---|
| AC-001 | S02-01 |
| AC-002 | S02-02 |
| AC-003 | S02-02 |
| AC-004 | S02-03 |
| AC-005 | S02-04 |

S02-01 的 Examples 只涵蓋轉換表中的 11 列；另外 4 列（`approval_invalidated`、`confirm_rerender`、`render_retry`、`render_failed_final`）與 AC-003 的窮舉由單元測試驗證（見 design.md）。

## 非功能需求

- 純領域邏輯：`app/domain/video.py` 不匯入資料庫、FastAPI 或任何外部服務。
- 轉換表以 dict 表示，不以一長串 if 判斷。
- 時間以時區感知的 UTC 記錄，時鐘可注入以便測試。

## 假設、風險與待決事項

1. **文件衝突：退回 `plan_ready` 的轉換。** 架構書 §6.1 的狀態圖沒有 `generating → plan_ready`，但 §6.3、開發計畫 S03（`ensure_still_approved` 觸發影片回到 `plan_ready`）與場景 S03-04、S06-06 都要求「核准失效時影片退回 `plan_ready`」。**使用者決定（2026-09-30）：採用 (A)**，在 S02 就加入 `generating --approval_invalidated--> plan_ready`，讓 S03／S06 不必修改 S02 的轉換表。架構書 §6.1 的圖之後需要同步更新。
2. **§6.1 有、但 S02-01 場景沒有的轉換**：合成相關的 3 個轉換（`rendering → rendering`、`rendering → needs_attention`、`needs_attention → rendering`）在 §6.1 圖中但不在場景 Examples 中。草稿依開發計畫「實作 §6.1」納入，以單元測試驗證。若希望場景也涵蓋，需要另開 CR 修改 `features/api/s02_video_state.feature`。
3. **事件名稱**：上述 4 個場景沒有的事件名稱（`approval_invalidated`、`render_retry`、`render_failed_final`、`confirm_rerender`）由草稿命名，使用者已確認照草稿。
4. **`failed` 為終止狀態**：依 §6.1，企劃產生失敗後這支影片無法恢復，使用者需重新建立影片。若希望能從 `failed` 重新送出主題，需修改架構書與本規格。
5. **只從 `generating` 退回 `plan_ready`**：`review → generating`（重生單鏡）之後的核准檢查也發生在 `generating`，因此不需要 `review → plan_ready`。`needs_attention` 確認重生後同樣先回到 `generating` 再檢查。
