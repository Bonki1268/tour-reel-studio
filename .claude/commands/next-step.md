---
description: 以 SDD＋BDD＋TDD 完成目前步驟：規格核准 → 紅燈 → 綠燈 → 閘門（自動 commit 與 push）
argument-hint: "[auto]  加上 auto 會在閘門通過後自動繼續，直到遇到需要使用者核准的地方"
---

依照 CLAUDE.md 與 `docx/spec-driven-development.md` 完成目前步驟。不可跳步、不可修改受保護檔案、不可代替使用者核准。

## 0. 了解現況

執行 `python3 scripts/tdd.py status` 與 `python3 scripts/tdd.py show`，依「下一個動作」決定從哪個階段開始。

## 1. S00 技術驗證（只有 S00）

協助使用者執行真實 API 驗證並整理**實測數據**到 `docx/validation/S00-report.md`。呼叫真實 API 或產生費用前，先取得使用者明確同意。「審核人」只能由使用者填寫。使用者填好後執行 `python3 scripts/tdd.py gate`。

## 2. Specify：規格草稿（規格尚未核准時）

1. 閱讀 `docx/development-plan.md` 的本步驟、`docx/system-architecture.md` 對應章節，以及 `features/` 中本步驟的場景。
2. 以 `specs/_template/` 建立或修訂 `specs/<package>/` 的 `spec.md`、`design.md`、`tasks.md`：
   - 需求 `R-xxx` 是使用者可觀察的行為；每個 `AC-xxx` 標明對應的 R，且可驗證
   - 「驗收對應」表把每個 AC 對應到場景編號；本步驟每個非 external 場景都要被對應
   - `design.md` 寫出測試策略；`tasks.md` 拆成可完成一次 red–green–refactor 的任務
   - 「狀態」保持 `draft`、「核准者／時間」保持 `TODO`
3. 執行 `python3 scripts/tdd.py spec`，修正到通過。
4. **停下來**。向使用者摘要：需求與驗收條件、重要設計取捨、未決問題。請使用者審閱後把「狀態」改為 `approved` 並填寫「核准者／時間」。**不要寫任何測試或產品程式碼。**

若發現 `features/` 的場景本身有誤、與架構書矛盾或無法實作：起草 `changes/CR-xxxx.md`（以 `changes/_template.md` 為範本），說明原因與建議，等待使用者處理。

## 3. Red：先寫測試（規格已核准）

1. 為本步驟每個場景寫步驟定義（後端 pytest-bdd，前端 playwright-bdd），並依 `tasks.md` 寫單元測試；測試名稱帶對應的 `R-xxx`（例如 `test_r002_hash_ignores_key_order`）。
2. 建立讓測試能被收集的最小骨架（介面、拋出 `NotImplementedError` 的函式），不寫實作邏輯。
3. 執行 `python3 scripts/tdd.py red`。它會檢查規格已核准、場景與單元測試齊全、測試確實失敗，並自動在本機 commit。

## 4. Green → Refactor

1. 只寫讓測試通過所需的最少程式碼；反覆執行本步驟的測試（例如 `cd backend && python -m pytest -m SNN`）。
2. 全綠後重構，每次修改都重跑測試。
3. 每完成 `tasks.md` 的一個任務，更新其追蹤矩陣的狀態欄。

## 5. Gate：驗證、commit、push

執行 `python3 scripts/tdd.py gate`。未通過就修正**程式碼**後重跑；不可修改、略過、xfail 或刪除測試。

通過後，閘門會自動：寫入 `specs/<package>/evidence.md`、把規格狀態改為 `implemented`、commit，並 push 到遠端。**不要自己執行 git commit 或 git push**，也不要 force push。

## 6. 回報

用三到五行回報：
- 完成的步驟與對應的 R／AC
- 測試數量與閘門結果
- commit 編號、是否已 push（若 push 失敗，照實說明原因）
- 下一步名稱

若參數包含 `auto`（目前參數：$ARGUMENTS），閘門通過後繼續下一步，直到需要使用者核准規格、S00／S19 報告需要使用者填寫，或閘門連續三次未通過為止。否則回報後停下。
