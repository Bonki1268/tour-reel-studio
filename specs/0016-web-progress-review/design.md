# 前端：進度與成品確認：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
apps/web/src/
├─ lib/
│  ├─ progress.ts     ProgressState、initialState、reduce(state, action)、fromSnapshot(video)
│  ├─ budget.ts       remaining(capStr, spentStr)、needsConfirmation(cost, remaining)、newCap(spent, cost)
│  └─ backoff.ts      backoffDelays()：1、2、4、8、15、15…；reset
├─ api/
│  ├─ client.ts       + regenerateShot(videoId, shotNo, costCap?)、approveFinal(videoId)、getDownload(videoId)
│  └─ reconnect.ts    subscribeWithReconnect(videoId, onEvent, onState, onReconnected)：EventSource onerror → 關閉 → 依退避重建
├─ components/
│  ├─ ShotProgress.tsx    鏡頭卡：生成進度、失敗訊息、重生按鈕與所需點數
│  ├─ RegenDialog.tsx     <dialog role="dialog">：剩餘預算、所需點數、新上限；確認／取消
│  └─ ResultPanel.tsx     <video controls src=preview_url>、下載、確認成品、已完成
└─ app/videos/[videoId]/page.tsx  useReducer(progress) ＋ 初次 GET ＋ SSE（含重連）
```

### reducer

reducer 的資料結構為 `{ status, shots: Record<number, "waiting"|"running"|"done"|"failed">, failedReason, previewUrl, connection: "open"|"lost" }`。

- 鏡頭進度只能前進：`waiting < running < done`；`failed` 可被之後的 `shot_started`（重生）蓋過。亂序保護：以事件時間 `at` 比較，同一鏡較舊的事件忽略；重生時新的 `shot_started` 讓該鏡由 done 回到 running。
- `fromSnapshot(video)`：以 `GET /videos/{id}` 的 `status`、`shots[].take.status`、`preview_url` 重建（重連後覆蓋）。

### 重生

`onRegenerate(shotNo)`：`cost = shot.regen_cost`；`remaining = cost_cap − spent`；`cost ≤ remaining` → `regenerateShot(id, no)`；否則開啟 `RegenDialog`，確認 → `regenerateShot(id, no, newCap(spent, cost))`。

### 下載

- `review`：`window.open(preview_url, "_blank")`（spec 待決事項 2）
- `approved`：`getDownload(id)` → `window.open(url, "_blank")`

### 後端（R-007）

- `schemas.ShotOut` 加 `regen_cost: Decimal`；`video_out` 以 `cost_table.price(KEYFRAME, hf_image_model) + price(VIDEO, hf_video_model)` 計算（與 S04 `estimate_video` 的單鏡成本相同）。
- `RegenerateIn(cost_cap: Decimal | None = None)`；路由：有 `cost_cap` 時檢查 `> video.cost_cap`（否則 422 `cap_not_raised`），呼叫 `orchestrator.raise_cost_cap(video_id, cost_cap, DEMO_USER)` 新增 PLAN 核准（沿用最新 PLAN 核准的 `input_hash`）並更新 `video.cost_cap`，再入列。
- `domain/approval.py` 新增 `raise_cap(previous: Approval, cost_cap, approved_by)`。

## 資料模型／狀態轉換變更

無資料表變更。`approvals` 多一筆 PLAN 紀錄；狀態機不變。

## API 契約（request／response、錯誤碼）

| 呼叫 | 說明 |
|---|---|
| `GET /videos/{id}` | `shots[].regen_cost`（新增） |
| `GET /videos/{id}/events` | `status`、`shot_started`、`shot_done`、`shot_failed`、`needs_attention`、`render_started`、`review_ready`、`render_failed`、`approved` |
| `POST /videos/{id}/shots/{no}/regenerate` | body 可選 `{cost_cap}`；422 `cap_not_raised` |
| `POST /videos/{id}/approve` | 成品確認 |
| `GET /videos/{id}/download` | `approved` 後的下載網址 |

## 失敗行為、安全與可觀測性

- API 失敗以 `role="alert"` 顯示後端訊息；按鈕恢復可按。
- SSE 中斷不視為錯誤，顯示連線情況並自動重連。
- 提高上限一律經使用者在對話框中明確同意。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S16-01）＋Unit | `apps/web/e2e/steps/s16.steps.ts`、`src/lib/progress.test.ts` |
| R-002 | AC-002 | BDD（S16-02） | 同上 |
| R-003 | AC-003 | BDD（S16-03） | 同上 |
| R-004 | AC-004 | BDD（S16-04）＋Unit | 同上、`src/lib/budget.test.ts` |
| R-005 | AC-005 | BDD（S16-05）＋Unit | 同上、`src/lib/backoff.test.ts` |
| R-006 | AC-006 | BDD（S16-06） | 同上 |
| R-007 | AC-007 | Unit（pytest） | `backend/tests/unit/test_regen_api.py` |

- E2E mock：進度頁的 SSE 以「每次連線送出一批事件後結束」模擬；步驟控制每次連線要送的事件。S16-05 先讓第一條連線以 `route.abort()` 中斷，檢查重連請求與 `GET /videos/{id}` 次數。
- `window.open` 以 `context.on("page")` 檢查開啟的網址。

預計單元測試（≥ 2，預計約 14）：
- `[S16] progress reducer`：依序、亂序、重複、重生、快照覆蓋
- `[S16] budget`：剩餘預算、是否需要確認、新上限（字串點數）
- `[S16] backoff`：序列與歸零
- pytest：`test_r007_regen_cost_in_video`、`test_r007_raise_cap_records_approval`、`test_r007_cap_not_raised_is_422`、`test_r007_without_body_unchanged`

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：超出剩餘預算的重生以「使用者確認提高成本上限」實作，記錄為新的 PLAN 核准；前端以 reducer 管理進度並在重連後以快照覆蓋。
- 替代方案：超出預算時禁止重生；由前端重新走完整企劃核准流程。
- 取捨：保留架構書「否則暫停並詢問」的行為，且每次提高上限都有核准紀錄可追溯；代價是 regenerate 端點多一個可選欄位。
