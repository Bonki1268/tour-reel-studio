# 前端：進度與成品確認：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-007／AC-007 | `backend/app/api/schemas.py`、`routes/videos.py`、`domain/approval.py`、`jobs/orchestrator.py`；重新產生 OpenAPI 型別 | `test_r007_*` | 測試通過 |
| T-02 | — | R-001／AC-001、R-004／AC-004、R-005／AC-005 | `src/lib/progress.ts`、`budget.ts`、`backoff.ts` | `[S16]` vitest | 測試通過 |
| T-03 | T-02 | R-001／AC-001、R-002／AC-002、R-005／AC-005 | `api/reconnect.ts`、`ShotProgress`、進度頁 | 場景 S16-01、S16-02、S16-05 | 測試通過 |
| T-04 | T-01、T-03 | R-004／AC-004 | `RegenDialog`、`api/client.ts` | 場景 S16-04 | 測試通過 |
| T-05 | T-03 | R-003／AC-003、R-006／AC-006 | `ResultPanel` | 場景 S16-03、S16-06 | 測試通過 |
| T-06 | T-01～T-05 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S15 回歸） |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S16-01` | `[S16] progress reducer` | `apps/web/src/lib/progress.ts`、`app/videos/[videoId]/page.tsx` | TODO |
| R-002 | AC-002 | `S16-02` | — | `apps/web/src/components/ShotProgress.tsx` | TODO |
| R-003 | AC-003 | `S16-03` | — | `apps/web/src/components/ResultPanel.tsx` | TODO |
| R-004 | AC-004 | `S16-04` | `[S16] budget` | `apps/web/src/lib/budget.ts`、`RegenDialog.tsx` | TODO |
| R-005 | AC-005 | `S16-05` | `[S16] backoff` | `apps/web/src/lib/backoff.ts`、`api/reconnect.ts` | TODO |
| R-006 | AC-006 | `S16-06` | — | `apps/web/src/components/ResultPanel.tsx` | TODO |
| R-007 | AC-007 | `S16-04` | `test_r007_*`（pytest） | `backend/app/api/routes/videos.py`、`domain/approval.py` | TODO |
