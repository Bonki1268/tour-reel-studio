# 前端：選題與企劃確認

狀態： approved
版本：v1
關聯開發步驟：S15
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

後端快速模式（S07～S14）已能從主題跑到成品，但業者還沒有畫面可用。本步驟建立 Next.js 前端的第一個確認點（架構書 §5.2 確認點 1）：業者輸入一句話主題（或點品牌賣點快速填入）、等待企劃、從 2–3 張企劃卡中選一案、在每鏡實景照上拖曳角色決定位置與大小（B1 擺放），勾選同意成本上限後核准，畫面進入生成進度頁。

所有 API 以 Playwright `page.route` mock 驗證（S19 才連真實後端）。

## 範圍內／範圍外

**範圍內**
- 建立 `apps/web`：Next.js（App Router）＋TypeScript、ESLint、vitest、@playwright/test、playwright-bdd、react-konva
- API 型別由後端 OpenAPI 產生（`openapi-typescript`），產生腳本與產物進 repo；前端不手寫 API 型別
- 頁面：`/projects/[projectId]`（選題與企劃確認）、`/videos/[videoId]`（生成進度頁的最小外殼，內容在 S16）
- 前端以同源路徑 `/api/*` 呼叫後端（Next.js rewrites 轉到 `API_BASE_URL`），SSE 以 `EventSource('/api/videos/{id}/events')` 接收
- **後端小幅補強（見待決事項 1）**：`GET /projects/{id}` 改為具型別的 `ProjectOut`，加上實景照與角色去背圖的預簽名網址，前端才能在實景照上顯示並拖曳角色

**範圍外**
- 進度、重生、成品播放與下載（S16）
- 品牌檔案編輯、實景照上傳（MVP 由種子資料準備）
- 登入（MVP 單一 Demo 帳號）、進階模式

## 使用者旅程

1. 業者打開 Demo 專案頁，看到店名、品牌賣點標籤與主題輸入框。
2. 輸入「清晨採梅體驗」或點賣點標籤「手作早餐」帶入主題，按「產生企劃」；畫面顯示「企劃產生中…」。
3. 收到 `plan_ready` 後顯示 2–3 張企劃卡：標題、概念、3 鏡摘要（角色／秒數／動作／字幕），以及預估點數、預留重生額度與成本上限。
4. 點選一張企劃卡，下方展開 3 鏡的實景照，角色以企劃建議的位置顯示；業者把角色拖到想要的位置、用滑桿調整大小、必要時左右翻轉。
5. 勾選「同意本次最高成本上限 N 點」後，「核准並開始生成」按鈕才可按；按下後送出核准，畫面跳到生成進度頁。

## 需求

- R-001：專案頁顯示主題輸入框；送出非空主題後呼叫 `POST /projects/{id}/videos`，畫面顯示「企劃產生中」，並訂閱該影片的 SSE；收到 `plan_ready` 事件後以 `GET /videos/{id}` 取得企劃並顯示 2–3 張企劃卡。空白主題不可送出。
- R-002：專案頁以標籤列出品牌賣點（`brand.selling_points`，字串或物件的 `title`）；點選標籤時把賣點文字加入主題輸入框（輸入框為空時直接填入，否則以「、」接在後面），不自動送出。
- R-003：每張企劃卡顯示企劃標題、概念與每鏡摘要（鏡號、角色、秒數、動作、字幕），以及預估點數、預留重生額度與成本上限；點數以千分位、最多 2 位小數顯示（例如 `1,234.5 點`）。
- R-004：選擇企劃後，每鏡顯示該鏡實景照與角色去背圖，角色初始位置為企劃建議的擺放；業者可拖曳角色（腳底中心跟隨）、以滑桿調整大小（照片高度的 10%–90%）、切換左右翻轉；擺放以照片座標比例值（0–1）記錄，與畫面顯示尺寸無關，角色腳底中心不可拖出照片。
- R-005：未勾選「同意成本上限」時核准按鈕停用；改選其他企劃時同意勾選自動取消（上限可能不同）。
- R-006：按下核准送出 `POST /videos/{id}/approve-plan`：標頭帶 `Idempotency-Key`（每次進入核准頁產生一次 UUID，重複點擊或重試沿用同一值），內容為 `plan_id`、`cost_cap`（該企劃的上限）與每鏡 `placements`（`{x, y, scale, flip}`）；送出期間按鈕停用；成功（202）後導向 `/videos/{id}`；失敗時顯示錯誤訊息並可重試。
- R-007：`GET /projects/{id}` 回傳具型別的 `ProjectOut`：專案、品牌檔案、鎖定角色（含去背圖的預簽名網址 `cutout_url`）與實景照（每張含預簽名網址 `url`、寬高）；沒有圖片物件時網址為 null。

## 驗收條件

- AC-001（對應 R-001）：Given 已開啟 Demo 專案頁且 API 以 mock 回應，When 輸入主題 "清晨採梅體驗" 並送出，Then 送出的 body 為 `{"topic": "清晨採梅體驗"}`、畫面顯示「企劃產生中」；When SSE 送出 `plan_ready`，Then 顯示與 mock 企劃數相同（2 或 3）張企劃卡。主題為空白時送出按鈕停用。
- AC-002（對應 R-002）：When 點選品牌賣點 "手作早餐"，Then 主題輸入框內容包含 "手作早餐"，且沒有送出請求；輸入框已有內容時以「、」接上。
- AC-003（對應 R-003）：Given 企劃已產生，Then 每張企劃卡有 3 個鏡頭摘要項目，並顯示預估點數與成本上限；`formatCredits("1234.5")` 為 `1,234.5 點`、`formatCredits("12")` 為 `12 點`、`formatCredits("0.125")` 為 `0.13 點`。
- AC-004（對應 R-004）：Given 已選擇第 1 個企劃，When 在第 1 鏡的實景照上把角色拖到右下方，Then 核准請求中第 1 鏡的 `x` > 0.5、`y` > 0.5；座標換算函式在照片縮放顯示（例如 1080×1920 顯示為 270×480）時，像素 ↔ 比例值互換結果一致（誤差 < 0.001），超出照片的座標被夾在 0–1。
- AC-005（對應 R-005）：Given 已選擇第 1 個企劃且尚未勾選同意成本上限，Then 核准按鈕為停用狀態；勾選後啟用；改選第 2 個企劃後再次停用。
- AC-006（對應 R-006）：Given 已選擇第 1 個企劃並勾選同意成本上限，When 按下核准，Then approve-plan 請求帶有非空的 `Idempotency-Key` 標頭，內容包含 `plan_id`、3 鏡的 `placements` 與 `cost_cap`，畫面進入生成進度頁；`buildApproveRequest` 組出的內容與標頭符合後端 `ApprovePlanIn` 型別，同一核准頁重送時 Idempotency-Key 不變。
- AC-007（對應 R-007）：Given 專案有角色去背圖與 3 張實景照，When `GET /projects/{id}`，Then 回應符合 `ProjectOut`，`character.cutout_url` 與每張 `scene_photos[].url` 為預簽名網址；物件不存在時為 null。前端以產生的 OpenAPI 型別讀取這些欄位。

## 驗收對應

| AC | 場景 |
|---|---|
| AC-001 | S15-01 |
| AC-002 | S15-02 |
| AC-003 | S15-03 |
| AC-004 | S15-04 |
| AC-005 | S15-05 |
| AC-006 | S15-06 |
| AC-007 | S15-04 |

AC-003 的格式函式、AC-004 的座標換算、AC-006 的請求組裝以 vitest 單元測試驗證；AC-007 的後端部分以 pytest 驗證（見待決事項 1）。

## 非功能需求

- 畫面在 390×844（手機）與 1280×800（桌機）都可操作；拖曳支援滑鼠與觸控（Konva 內建）。
- 介面文字為繁體中文。
- `npm run lint`（ESLint）與 `tsc --noEmit` 無錯誤（閘門檢查）。
- 測試不連外：E2E 以 `page.route` mock 所有 `/api/*`，SSE 以回應串流模擬。

## 假設、風險與待決事項

1. **後端補強與閘門（需要決定）。** 前端拖曳角色必須取得實景照與去背圖的網址，但現有 `GET /projects/{id}` 只回傳 storage key 且沒有型別。S15 在 `.tdd/progress.json` 只有 web、e2e 測試套件，閘門**不會執行**標記為 S15 的 pytest。建議：
   - **方案 A（建議）**：核准 `changes/CR-0001.md`，由你以 `tdd.py unlock` 把 S15 的套件加上 `py`，後端補強（R-007）就能在本步驟以 pytest 驗證。
   - 方案 B：R-007 移到 S17（py 步驟，種子資料時一起補），S15 前端先依 `ProjectOut` 契約撰寫並以 mock 測試；但 OpenAPI 型別要到 S17 後才完整，S15 期間 `GET /projects` 的型別需暫時手寫。
2. **同源 `/api` 代理。** 前端一律呼叫 `/api/*`，由 Next.js rewrites 轉到 `API_BASE_URL`（預設 `http://localhost:8000`）；瀏覽器不需要 CORS，E2E mock 也只攔截 `/api/*`。
3. **Demo 專案入口。** `/` 導向 `/projects/${NEXT_PUBLIC_DEMO_PROJECT_ID}`；種子資料（S17）決定專案 ID。
4. **縮放範圍。** 滑桿 10%–90%（後端 `scale` 上限為 1）；企劃建議值超出時夾到範圍內。
5. **SSE 模擬。** Playwright 的 `route.fulfill` 一次回傳完整事件串流；需要先看到「產生中」再送 `plan_ready` 時，步驟定義延後 fulfill。
6. **工具安裝。** 需要從 npm 安裝 Next.js 等套件，並下載 Playwright 的 Chromium（約 150 MB），皆免費。
7. **企劃 payload 型別。** 後端 `PlanOut.payload` 為未定型 JSON；前端以 S10 `PlansOut` 的欄位（title、concept、shots[].{shot_no, role, duration_s, scene_photo_id, placement, action, subtitle}）在一個轉換函式中檢查後使用，缺欄位時顯示「—」。
