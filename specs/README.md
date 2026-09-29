# Spec packages

依 `docx/spec-driven-development.md`，每個開發步驟對應一個 spec package。沒有已核准（approved）的 spec，就不能開始寫測試與程式碼；`scripts/tdd.py red` 會檢查。

| 步驟 | Package | 步驟 | Package |
|---|---|---|---|
| S01 | `0001-project-foundation` | S11 | `0011-b1-photo-composite` |
| S02 | `0002-video-state-machine` | S12 | `0012-higgsfield-adapter` |
| S03 | `0003-approval-invalidation` | S13 | `0013-timeline-render` |
| S04 | `0004-cost-budget` | S14 | `0014-outro-card` |
| S05 | `0005-persistence` | S15 | `0015-web-plan-confirm` |
| S06 | `0006-generation-job` | S16 | `0016-web-progress-review` |
| S07 | `0007-quick-mode-orchestration` | S17 | `0017-demo-seed` |
| S08 | `0008-rest-api-sse` | S18 | `0018-demo-reliability` |
| S09 | `0009-object-storage` | S19 | `0019-e2e-acceptance` |
| S10 | `0010-prompt-engine` | | |

S00（技術驗證）沒有 spec package，證據為 `docx/validation/S00-report.md`。

## 每個 package 的檔案

| 檔案 | 誰寫 | 說明 |
|---|---|---|
| `spec.md` | Claude Code 起草，使用者核准 | 需求 R-xxx、驗收條件 AC-xxx、AC 與場景的對應 |
| `design.md` | Claude Code | 設計、契約、測試策略、ADR |
| `tasks.md` | Claude Code | 任務與需求追蹤矩陣 |
| `evidence.md` | `scripts/tdd.py` 自動寫入；人工驗收由使用者填寫 | 閘門紀錄、人工驗收 |

## 與 features/ 的關係

BDD 場景只存在 `features/`（測試的執行入口），不另外維護 `acceptance.feature`，避免兩份規格漂移。`spec.md` 的「驗收對應」表把每個 AC 連到場景編號（例如 `S02-01`），閘門會雙向檢查：

- 每個 AC 至少對應一個場景
- 本步驟每個非 external 場景都被至少一個 AC 對應

## 狀態流程

`draft`（Claude 起草）→ `approved`（使用者核准）→ `implemented`（閘門通過後由 tdd.py 自動更新）→ `validated`（使用者完成人工驗收後自行更新）
