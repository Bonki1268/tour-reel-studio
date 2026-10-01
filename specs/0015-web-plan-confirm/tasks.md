# 前端：選題與企劃確認：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-007／AC-007 | `backend/app/api/schemas.py`、`routes/projects.py`、`backend/scripts/export_openapi.py` | `test_r007_*` | 測試通過 |
| T-02 | T-01 | — | 建立 `apps/web`（Next.js、ESLint、vitest、Playwright、playwright-bdd、react-konva）、`gen:api` 產生型別 | — | `npm run lint`、`tsc --noEmit` 通過，`npx bddgen` 可執行 |
| T-03 | T-02 | R-003／AC-003、R-004／AC-004、R-006／AC-006、R-002／AC-002 | `src/lib/*` | `[S15]` vitest | 測試通過 |
| T-04 | T-03 | R-001／AC-001、R-002／AC-002、R-003／AC-003 | `TopicForm`、`PlanCard`、專案頁、`api/client.ts`、`api/events.ts` | 場景 S15-01、S15-02、S15-03 | 測試通過 |
| T-05 | T-04 | R-004／AC-004 | `PlacementEditor` | 場景 S15-04 | 測試通過 |
| T-06 | T-05 | R-005／AC-005、R-006／AC-006 | `ApprovePanel`、進度頁外殼 | 場景 S15-05、S15-06 | 測試通過 |
| T-07 | T-01～T-06 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S14 回歸） |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S15-01` | — | `apps/web/src/app/projects/[projectId]/page.tsx`、`src/api/*` | TODO |
| R-002 | AC-002 | `S15-02` | `[S15] sellingPointLabels` | `apps/web/src/components/TopicForm.tsx`、`src/lib/plan.ts` | TODO |
| R-003 | AC-003 | `S15-03` | `[S15] formatCredits` | `apps/web/src/components/PlanCard.tsx`、`src/lib/format.ts` | TODO |
| R-004 | AC-004 | `S15-04` | `[S15] placement` | `apps/web/src/components/PlacementEditor.tsx`、`src/lib/placement.ts` | TODO |
| R-005 | AC-005 | `S15-05` | — | `apps/web/src/components/ApprovePanel.tsx` | TODO |
| R-006 | AC-006 | `S15-06` | `[S15] buildApproveRequest` | `apps/web/src/lib/approve.ts`、`ApprovePanel.tsx` | TODO |
| R-007 | AC-007 | `S15-04` | `test_r007_*`（pytest） | `backend/app/api/routes/projects.py`、`schemas.py` | TODO |
