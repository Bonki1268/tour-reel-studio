# 前端：選題與企劃確認：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
apps/web/
├─ package.json            scripts：dev、build、lint、typecheck、test（vitest）、e2e、gen:api
├─ next.config.ts          rewrites：/api/:path* → ${API_BASE_URL}/:path*
├─ playwright.config.ts    defineBddConfig({ features: "../../features/web/**/*.feature", steps: "e2e/steps/**/*.ts" })
│                          webServer：next dev（port 3100）
├─ vitest.config.ts        jsdom；只收 src/**/*.test.ts(x)
├─ src/
│  ├─ api/
│  │  ├─ openapi.json      由 scripts/export_openapi.py 匯出（進 repo）
│  │  ├─ schema.d.ts       openapi-typescript 產生（進 repo）
│  │  ├─ client.ts         fetch 包裝：getProject、createVideo、getVideo、approvePlan（型別來自 schema.d.ts）
│  │  └─ events.ts         subscribe(videoId, onEvent)：EventSource 包裝
│  ├─ lib/
│  │  ├─ placement.ts      toRatio／toPixels／clampPlacement／characterBox
│  │  ├─ format.ts         formatCredits
│  │  ├─ approve.ts        buildApproveRequest（plan、placements、idempotencyKey）
│  │  └─ plan.ts           parsePlan（未定型 payload → PlanView）、sellingPointLabels
│  ├─ components/
│  │  ├─ TopicForm.tsx     輸入框、賣點標籤、送出
│  │  ├─ PlanCard.tsx      企劃摘要與成本
│  │  ├─ PlacementEditor.tsx  react-konva：實景照、可拖曳角色、大小滑桿、翻轉（client only，dynamic import）
│  │  └─ ApprovePanel.tsx  同意勾選、核准按鈕、錯誤訊息
│  └─ app/
│     ├─ page.tsx                  redirect → /projects/${NEXT_PUBLIC_DEMO_PROJECT_ID}
│     ├─ projects/[projectId]/page.tsx   選題 → 企劃 → 擺放 → 核准（client component 狀態機）
│     └─ videos/[videoId]/page.tsx       生成進度頁外殼（標題「生成中」，S16 補內容）
└─ e2e/
   ├─ steps/s15.steps.ts
   └─ support/mockApi.ts   fixtures：專案、影片（planning／plan_ready）、企劃 3 張、SSE 控制
```

### 頁面狀態

`idle → submitting → planning（顯示「企劃產生中」）→ plans_ready（企劃卡）→ plan_selected（擺放＋核准）→ approving → 導向 /videos/{id}`

### 擺放座標

照片以容器寬度等比顯示（`displayW = min(containerW, 360)`、`displayH = displayW × photoH / photoW`）。
- `toRatio({px, py}, display) = {x: clamp(px / displayW), y: clamp(py / displayH)}`
- `toPixels({x, y}, display) = {px: x × displayW, py: y × displayH}`
- 角色節點：高度 `scale × displayH`、寬度依去背圖長寬比；節點 offset 設在腳底中心，拖曳時以 `dragBoundFunc` 夾在照片內。
- 角色圖、照片載入失敗時以灰色剪影矩形代替（仍可拖曳）。

### Idempotency-Key

進入 `plan_selected` 時以 `crypto.randomUUID()` 產生並存在元件狀態；核准失敗重試沿用；改選企劃時重新產生（內容不同）。

### 後端補強（R-007）

- `schemas.py` 新增 `BrandOut`、`CharacterOut(id, version, anchor_card, cutout_url)`、`ScenePhotoOut(id, image_key, url, width, height, description)`、`ProjectOut`。
- `routes/projects.py` 以 `storage.presign_get(key, presign_ttl_s)` 產生網址；`ObjectNotFound` → null。
- `scripts/export_openapi.py`（backend）匯出 `create_app` 的 OpenAPI 到 `apps/web/src/api/openapi.json`；`npm run gen:api` 產生 `schema.d.ts`。

## 資料模型／狀態轉換變更

無資料表變更。`GET /projects/{id}` 回應加上網址欄位（只增不減，既有欄位保留）。

## API 契約（request／response、錯誤碼）

| 呼叫 | 用途 |
|---|---|
| `GET /projects/{id}` → `ProjectOut` | 店名、賣點、角色去背圖網址、實景照網址與寬高 |
| `POST /projects/{id}/videos` `{topic}` → 201 `VideoOut` | 建立影片 |
| `GET /videos/{id}/events`（SSE） | `status`、`plan_ready`、`planning_failed` |
| `GET /videos/{id}` → `VideoOut` | 企劃與成本估算 |
| `POST /videos/{id}/approve-plan` `Idempotency-Key` `{plan_id, cost_cap, placements}` → 202 | 核准 |

錯誤：4xx／5xx 顯示後端 `message`（沒有時顯示「發生錯誤，請稍後再試」）；`planning_failed` 事件顯示「企劃產生失敗」與重試按鈕（重新送出主題）。

## 失敗行為、安全與可觀測性

- 前端不接觸任何金鑰；圖片以短期預簽名網址載入。
- 核准重送沿用同一 Idempotency-Key，後端不會重複扣點。
- 網路錯誤時按鈕恢復可按，錯誤訊息以 `role="alert"` 呈現。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S15-01） | `apps/web/e2e/steps/s15.steps.ts` |
| R-002 | AC-002 | BDD（S15-02）＋Unit | 同上、`apps/web/src/lib/plan.test.ts` |
| R-003 | AC-003 | BDD（S15-03）＋Unit | 同上、`apps/web/src/lib/format.test.ts` |
| R-004 | AC-004 | BDD（S15-04）＋Unit | 同上、`apps/web/src/lib/placement.test.ts` |
| R-005 | AC-005 | BDD（S15-05） | 同上 |
| R-006 | AC-006 | BDD（S15-06）＋Unit | 同上、`apps/web/src/lib/approve.test.ts` |
| R-007 | AC-007 | Unit（pytest）＋BDD（S15-04 使用網址欄位） | `backend/tests/unit/test_project_api.py` |

- E2E：每個場景以 `mockApi` 設定 `page.route('**/api/**')`；SSE 路由回傳 `text/event-stream`，`plan_ready` 由步驟控制何時送出。核准請求由 mock 記錄後在 Then 步驟檢查。
- 拖曳：取得 canvas 的 bounding box，依 mock 的初始擺放算出角色腳底附近的點，以 `page.mouse` 拖到照片右下 80% 處。
- 單元測試名稱以 `[S15]` 開頭（閘門以此計數）。

預計單元測試（≥ 2，預計約 15）：
- `[S15] placement`：比例↔像素互換、縮放顯示、夾在 0–1、角色框計算
- `[S15] formatCredits`：千分位、小數、字串輸入
- `[S15] buildApproveRequest`：內容、標頭、重送沿用同一 key、改選企劃產生新 key
- `[S15] sellingPointLabels／appendTopic`：字串與物件賣點、以「、」接續
- `[S15] parsePlan`：缺欄位時的預設值
- pytest `test_r007_project_has_presigned_urls`、`test_r007_missing_objects_null`

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：前端以同源 `/api` 代理呼叫後端；API 型別由 OpenAPI 產生並進 repo；`GET /projects/{id}` 改為具型別回應並附預簽名網址。
- 替代方案：前端直接呼叫後端網域（需 CORS）；手寫 API 型別；前端另呼叫預簽名端點取得每張圖網址。
- 取捨：同源代理讓 mock 與部署一致、不需 CORS；產生的型別讓後端欄位變更在 `tsc` 階段就被發現，代價是後端改 schema 時要重跑 `gen:api`；一次回傳所有網址減少往返，代價是專案回應稍大且網址有效期 15 分鐘（頁面停留過久需重新整理）。
