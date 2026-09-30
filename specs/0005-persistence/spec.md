# 資料持久化

狀態：implemented
版本：v1
關聯開發步驟：S05
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

S02～S04 的狀態機、核准與成本帳目前只存在記憶體中。業者的專案、品牌檔案、企劃、每一鏡的每個版本、生成工作與成本帳都必須可靠保存：Worker 重啟後要能繼續，重生鏡頭時舊版本不能遺失，同一個生成工作不能因為重送而重複建立（重複扣點）。

本步驟以 SQLAlchemy＋Alembic 在 PostgreSQL 上實作架構書 §7 的資料模型，並在 `app/domain/ports.py` 定義 repository 介面，提供資料庫版與記憶體版兩種實作。

## 範圍內／範圍外

**範圍內**
- `infra/docker-compose.test.yml`（PostgreSQL、Redis；Redis 供 S06 使用。S3 相容儲存見待決事項 8）
- Alembic 遷移：從空資料庫建立架構書 §7 的 14 張資料表
- repository 介面與兩種實作：專案＋品牌檔案、影片（含狀態歷程與時間軸）、鏡頭＋鏡頭版本、生成工作、核准紀錄、成本帳
- 生成工作冪等鍵 `video:shot:kind:hash:attempt` 的組成函式與唯一性保證
- 設定新增 `DATABASE_URL`

**範圍外**
- 使用者、角色、實景照、企劃、成品的 repository（S08、S10、S11、S13、S17 用到時再加入；資料表本步驟就建立）
- 並行更新的樂觀鎖、跨 repository 的交易邊界（S06／S07 規格決定）
- Redis 佇列（S06）、物件儲存（S09）
- 正式環境的資料庫部署與備份

## 使用者旅程

本步驟沒有新的使用者介面。業者可觀察到的結果：

1. 重新整理頁面、或伺服器重啟後，專案、品牌檔案、影片狀態與時間軸都還在。
2. 某一鏡重生後，之前的版本仍保留，可以回頭比較。
3. 網路不穩造成同一個生成請求被送兩次時，系統只建立一個生成工作，不會重複扣點。

## 需求

- R-001：從空的資料庫執行所有 Alembic 遷移後，架構書 §7 的 14 張資料表全部存在；遷移可以完整降版回空資料庫。
- R-002：建立的專案與品牌檔案寫入後可以完整讀回，JSON 欄位（視覺、賣點、資訊、來源）的內容與型別不變。
- R-003：鏡頭重生時新增一個版本（`attempt` 遞增），鏡頭的目前版本指向新版本，所有舊版本仍可讀取。
- R-004：生成工作以冪等鍵 `{video_id}:{shot_no}:{kind}:{input_hash}:{attempt}` 識別；以相同冪等鍵再次建立時回傳既有的工作，不建立新的紀錄。
- R-005：影片的時間軸 JSON 與角色擺放 JSON 儲存後重新讀取，內容與型別（整數、浮點數、字串、布林、巢狀結構、陣列順序）完全相同。
- R-006：記憶體版與資料庫版 repository 對同一組操作的結果一致，供之後的單元測試使用記憶體版取代資料庫。
- R-007：影片的狀態與狀態歷程（S02）、核准紀錄（S03）、成本帳（S04）寫入後可以讀回為相同的領域物件。

## 驗收條件

- AC-001（對應 R-001）：Given 一個空的資料庫，When 執行 `alembic upgrade head`，Then `users`、`projects`、`brand_profiles`、`characters`、`character_versions`、`scene_photos`、`videos`、`plans`、`shots`、`shot_takes`、`generation_jobs`、`approvals`、`cost_entries`、`renders` 全部存在；再執行 `alembic downgrade base` 後這些資料表都不存在。
- AC-002（對應 R-002）：Given 一個已遷移的空資料庫，When 建立專案「梅子農場」並寫入品牌檔案（含巢狀 JSON 與中文），Then 以專案 ID 讀回的專案與品牌檔案與寫入內容相等。
- AC-003（對應 R-003）：Given 一支影片的第 1 鏡已有 1 個版本，When 第 1 鏡重生，Then 第 1 鏡有 2 個版本（attempt 1、2），目前版本指向 attempt 2，且 attempt 1 的內容仍可讀取且未被修改。
- AC-004（對應 R-004）：Given 已存在冪等鍵為 `v1:1:keyframe:abc:1` 的生成工作，When 再次建立相同冪等鍵的生成工作（其他欄位不同），Then 回傳既有工作（ID 與欄位皆為原本的值），資料表中該冪等鍵只有 1 筆。
- AC-005（對應 R-004）：`idempotency_key(video_id="v1", shot_no=1, kind="keyframe", input_hash="abc", attempt=1)` 回傳 `"v1:1:keyframe:abc:1"`；任一組成部分為空、含冒號，或 `shot_no`／`attempt` 小於 1 時拋出錯誤。
- AC-006（對應 R-005）：Given 一支影片有一份時間軸 JSON（含整數、浮點數、中文字串、布林、巢狀物件與有順序的陣列），When 儲存後重新讀取，Then 與原本內容相等，且每個值的 Python 型別相同；擺放 JSON 同樣成立。
- AC-007（對應 R-006）：同一組 repository 測試以參數化分別對記憶體版與資料庫版執行，結果全部相同。
- AC-008（對應 R-007）：影片經過 `submit_topic`、`plans_ready` 後儲存再讀回，狀態與狀態歷程（事件、前後狀態、時間）相同；核准紀錄與成本帳（`Decimal` 點數）讀回後與寫入的領域物件相等。

## 驗收對應

| AC | 場景 |
|---|---|
| AC-001 | S05-01 |
| AC-002 | S05-02 |
| AC-003 | S05-03 |
| AC-004 | S05-04 |
| AC-005 | S05-04 |
| AC-006 | S05-05 |
| AC-007 | S05-02 |
| AC-008 | S05-05 |

AC-005、AC-007、AC-008 與 AC-006 的型別檢查以單元／整合測試驗證（見 design.md）。

## 非功能需求

- 領域層（`app/domain/`）不匯入 SQLAlchemy；ORM 模型與對應只在 `app/storage/`。
- 資料庫連線字串只從設定（`DATABASE_URL`）讀取，不寫在程式或測試中；測試用的連線字串由 `infra/docker-compose.test.yml` 決定。
- 整合測試彼此獨立：每個測試使用乾淨的資料庫狀態，不依賴執行順序。
- 點數欄位使用 `NUMERIC`，讀回為 `Decimal`，不經過浮點數。

## 假設、風險與待決事項

1. **Docker（已解決）。** S05 的場景都是 `@integration`，閘門會自動執行 `docker compose -f infra/docker-compose.test.yml up -d --wait`。使用者決定（2026-09-30）由使用者自行安裝；2026-10-01 確認 Docker 29.8.1、Compose v5.5.1 可用，`postgres:16`、`redis:7` 映像可以拉取。
2. **狀態歷程的保存方式。** §7 沒有狀態歷程的資料表。草稿在 `videos` 加一個 `status_history`（JSONB）欄位保存 S02 的 `StatusChange` 清單，不新增資料表。
3. **生成工作的冪等鍵欄位。** §7 的 `generation_jobs` 沒有列出冪等鍵欄位（只有 `provider_idempotency_key`，用途是呼叫 Higgsfield 時的冪等，見 §6.2）。草稿新增 `idempotency_key` 欄位並設唯一索引；兩者用途不同、並存。
4. **主鍵型別。** 草稿使用 UUID 字串作為主鍵；冪等鍵中的 `video_id` 即影片的 UUID。場景中的 `v1` 只是測試用的 ID。
5. **同步或非同步資料庫存取。** FastAPI 與 arq 都是 async，草稿採用 SQLAlchemy 2.0 async＋psycopg 3（同一個驅動也供 Alembic 同步執行遷移）；repository 介面全部是 `async`，記憶體版亦同。
6. **`DATABASE_URL` 不列入正式模式必要設定。** 加入必要清單會改變 S01 已實作規格的 R-003，需要另開 CR；草稿不加入，正式環境連不上資料庫時於第一次存取時失敗。若希望啟動時就檢查，請告訴我，我會起草 CR。
7. **資料表欄位以 §7 為準**，只增加上述 `status_history`、`idempotency_key` 與必要的 `created_at`；欄位若之後步驟需要調整，以新的 Alembic 遷移處理。
8. **MinIO 映像無法取得（已決定）。** 2026-10-01 實測 `minio/minio`（含舊版固定標籤）、`quay.io/minio/minio`、`bitnami/minio` 都拉不到。**使用者決定（2026-10-01）：採用 (A)**，S05 的 compose 只放 PostgreSQL＋Redis，S3 相容儲存的映像留到 S09 規格再決定（屆時若偏離架構書 §4 的 MinIO，另開 CR）。
