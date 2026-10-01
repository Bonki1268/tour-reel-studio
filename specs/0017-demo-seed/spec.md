# Demo 種子資料

狀態：implemented
版本：v1
關聯開發步驟：S17
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

Demo 現場不能臨時建立專案、上傳照片或依賴網路擷取（架構書 §9.3）。本步驟提供可重複執行的種子腳本：從 `seed/demo/` 的品牌資料、Logo、角色身份板與去背圖、3–5 張實景照建立一個已確認品牌檔案、已鎖定角色的 Demo 專案；官網品牌資訊只用快取檔（不在現場呼叫 Firecrawl）。重複執行不會產生重複資料，前端以固定的專案 ID 打開 Demo 專案。

## 範圍內／範圍外

**範圍內**
- `seed/demo/`：`demo.json`（品牌、角色、實景照描述）與圖片檔；`seed/cache/firecrawl-<domain>.json`
- `backend/app/seed/`：`schema.py`（種子 JSON 的 Pydantic 模型）、`firecrawl.py`（擷取結果 → 品牌檔案欄位、快取讀寫）、`assets.py`（圖片前處理）、`run.py`（`python -m app.seed.run`）
- 圖片前處理：實景照依 EXIF 轉正、置中裁成 9:16、縮成 1080×1920 JPEG；去背圖裁掉腳底下方的透明邊（保留上、左、右透明邊）
- 冪等：專案 ID 由專案名稱以 UUIDv5 產生；角色版本、實景照以檔案內容雜湊判斷是否已存在
- Repository 補上種子需要的查詢（依 ID 取得專案是否存在、角色版本、實景照清單已存在）

**範圍外**
- 前端上傳實景照、編輯品牌檔案
- 自動去背（架構書 §14.1 #1：MVP 在種子階段準備好）
- 在閘門中呼叫真實 Firecrawl（`--refresh-firecrawl` 只在使用者同意時手動執行）

## 使用者旅程

1. 開發者（或 Demo 前的準備者）把店家素材放進 `seed/demo/`，執行 `python -m app.seed.run`。
2. 腳本印出 Demo 專案 ID；前端設定 `NEXT_PUBLIC_DEMO_PROJECT_ID` 後，打開首頁即進入 Demo 專案。
3. Demo 前重跑一次腳本確認環境；資料已存在時不重複建立，只補上缺少的物件。
4. 需要更新官網品牌資訊時，在有網路且同意費用時執行 `python -m app.seed.run --refresh-firecrawl` 更新快取檔。

## 需求

- R-001：執行種子腳本後，存在一個品牌檔案已確認（`confirmed_at` 有值）的 Demo 專案：店名、語氣、賣點、地址、訂位網址、品牌主色與 Logo 來自 `demo.json` 與官網擷取快取；專案 ID 為 `uuid5(NAMESPACE_URL, "tour-reel-studio:" + 專案名稱)`，腳本結束時印出。
- R-002：專案有 1 個已鎖定的角色版本，身份板與去背全身圖存於自有儲存（`keys.identity_board`、`keys.cutout`），錨點卡含中英文外觀描述。
- R-003：專案有 3 到 5 張實景照，每張有文字描述；圖片已依 EXIF 轉正、置中裁成 9:16 並縮成 1080×1920 JPEG 後存入自有儲存（`keys.scene_photo`），紀錄的寬高為 1080×1920。
- R-004：重複執行種子腳本不產生重複的專案、角色或實景照；素材檔內容改變時新增對應的角色版本或實景照（舊的保留），品牌檔案以最新內容更新。
- R-005：官網品牌資訊只從 `seed/cache/firecrawl-<domain>.json` 讀取；沒有快取時以 `demo.json` 為準並印出警告，不連網。加上 `--refresh-firecrawl` 且設定 `FIRECRAWL_API_KEY` 時才呼叫 Firecrawl 並寫回快取；呼叫失敗時保留舊快取並結束時回報失敗，不中斷建立專案。
- R-006：角色去背圖存為含 alpha 通道的 PNG，四個角落完全透明；腳底下方的透明邊被裁掉（不透明範圍的下緣即圖片下緣），讓前端擺放時看到的腳底位置與 B1 合成一致。
- R-007：種子 JSON 不符合 schema（缺欄位、實景照少於 3 或多於 5 張、圖片檔不存在、去背圖沒有透明背景）時，腳本在寫入任何資料前停止，並列出所有問題。

## 驗收條件

- AC-001（對應 R-001、R-002、R-003）：Given 一個已遷移的空資料庫與空的物件儲存（整合測試：PostgreSQL＋MinIO），When 以測試素材目錄執行種子腳本，Then 存在 ID 為預期 UUIDv5 的專案且 `confirmed_at` 有值；有 1 個鎖定角色版本，身份板與去背圖物件存在；有 3 到 5 張實景照，每張描述非空、物件存在、寬高 1080×1920。
- AC-002（對應 R-004）：Given 種子腳本已執行過一次，When 再次執行，Then 專案、角色版本與實景照的數量不變；When 替換其中一張實景照的檔案後再執行，Then 實景照多一張且舊的保留。
- AC-003（對應 R-005）：Given Firecrawl 無法連線（未設定金鑰，或 HTTP mock 回應連線錯誤）且存在官網擷取快取檔，When 執行種子腳本，Then 成功完成，品牌主色、Logo 與訂位網址取自快取；沒有快取時仍成功並以 `demo.json` 為準。單元測試：Firecrawl `branding` 回應轉換為品牌欄位（colors、logo、fonts）；`--refresh-firecrawl` 失敗時快取檔不變。
- AC-004（對應 R-006）：When 執行種子腳本，Then 自有儲存中的去背圖為 mode `RGBA` 的 PNG，四個角落 alpha 為 0，不透明範圍下緣等於圖片高度。
- AC-005（對應 R-003）：單元測試：4284×5712（帶 EXIF 旋轉）的照片處理後為 1080×1920，且內容為置中裁切。
- AC-006（對應 R-007）：單元測試：`demo.json` 缺少店名、實景照只有 2 張、圖片檔不存在、去背圖不透明時，驗證錯誤列出每個問題，資料庫與儲存沒有任何寫入。

## 驗收對應

| AC | 場景 |
|---|---|
| AC-001 | S17-01 |
| AC-002 | S17-02 |
| AC-003 | S17-03 |
| AC-004 | S17-04 |
| AC-005 | S17-01 |
| AC-006 | S17-01 |

S17 場景為 `@integration`（PostgreSQL＋MinIO，閘門自動啟動）。AC-003 的 Firecrawl 轉換、AC-005、AC-006 以單元測試驗證。

## 非功能需求

- 種子腳本在一般開發機上 30 秒內完成（含圖片前處理）。
- 測試素材以程式產生，不依賴 `seed/demo/` 的真實檔案。
- 金鑰只從環境變數讀取；快取檔不含金鑰。

## 假設、風險與待決事項

1. **Demo 素材來源（需要決定）。** 草稿建議沿用 S00 驗證用的「古堡 1624 咖啡館」素材（`spikes/higgsfield/inputs/`：3 張安平古堡實景照、鄭成功身份板與去背圖、品牌資料），前處理後放進 `seed/demo/`。這些是你的手機照片與 AI 生成角色，會隨 repo push 到遠端（處理後每張約 0.3–1 MB）。若不希望進 repo，可改為 `seed/demo/` 列入 `.gitignore`，由 Demo 前手動放入；閘門測試只用程式產生的素材，不受影響。
2. **S00 已知限制。** 現有實景照都是古堡園區景點、沒有咖啡館本身；營業時間為虛構。正式 Demo 前建議補咖啡館照片（S00 報告結論）。
3. **官網擷取快取。** 需要店家官網網域與一次真實 Firecrawl 呼叫（產生費用，需你同意）才能產生真實快取；在那之前 `seed/cache/` 以 `demo.json` 的品牌資料手寫一份等價快取（標註為手動建立），種子腳本行為不變。
4. **訂位網址。** S14 的片尾 QR code 讀 `info.booking_url`；`demo.json` 需填入（S00 品牌資料沒有）。
5. **去背圖只裁下緣。** 保留上、左、右透明邊，確保 S17-04「四角透明」成立，同時讓腳底對齊（S15 已知限制）。
6. **專案 ID 固定。** 以專案名稱產生 UUIDv5，前端 `NEXT_PUBLIC_DEMO_PROJECT_ID` 可寫在 `.env.example`。
