# 企劃產生 PromptEngine

狀態：implemented
版本：v1
關聯開發步驟：S10
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

S07 的企劃來自固定內容的假引擎。業者輸入一句主題後，需要看到 2～3 個真正依自家品牌、角色與實景照量身寫的 15 秒企劃，而且每個企劃都必須能直接交給生成流程：固定 3 鏡（鉤子 → 特色 → 行動呼籲）、長度合計 12 秒（片尾卡 3 秒另計）、只使用專案裡真的有的實景照、擺放參數在合理範圍內。

本步驟實作 `PromptEngine`：以 tourism-promo 模板組出提示詞，呼叫 Claude 取得結構化 JSON，先以 Pydantic 驗證結構、再做語意驗證，不合格時重試一次；並依企劃產生每鏡的關鍵幀與影片提示詞。S00 的 `spikes/higgsfield/tourism_promo.py` 與 `results/v4_claude_prompt.md` 是模板的起點。

## 範圍內／範圍外

**範圍內**
- `backend/app/creative/skills/tourism-promo/SKILL.md`：題材規則（15 秒、3 鏡、鉤子→特色→行動呼籲、繁體中文、字幕長度、運鏡寫法）
- `PromptEngine`（實作 S07 的 `CreativeEngine`）：組提示詞、呼叫 Claude、Pydantic 驗證、語意驗證、重試一次
- `ClaudeClient` 介面與 Anthropic SDK 實作；測試以預錄 fixture 注入
- 每鏡生成提示詞（關鍵幀、影片），由企劃與角色錨點依模板組成，不另外呼叫 Claude
- 設定：`CLAUDE_MODEL`、`CLAUDE_EFFORT`、`CREATIVE_ENGINE`（`prompt`／`fake`）
- `@external` 測試：以真實 Claude 產生一次企劃（不列入閘門，需使用者同意與金鑰）

**範圍外**
- DramaSkillsEngine（第二階段）
- B1 粗合成圖（S11）、Higgsfield 呼叫（S12）
- 企劃內容的人工品質評估（S19 以真實 API 驗收）

## 使用者旅程

1. 業者輸入主題「清晨採梅體驗」。
2. 約數十秒後看到 2～3 個企劃，每個都有標題、概念、3 鏡的場景、動作、字幕與運鏡，場景都是自家的實景照。
3. 若 Claude 偶爾回傳格式錯誤或引用不存在的照片，系統自動再試一次，業者不會看到錯誤的企劃；連續兩次都不合格時，影片顯示「企劃產生失敗」，可重新產生。

## 需求

- R-001：以主題產生 2～3 個企劃；每個企劃有 3 鏡，功能依序為 `hook`、`feature`、`cta`，長度合計 12 秒，每鏡引用的實景照都存在於專案中，擺放參數 `x`、`y` 介於 0 到 1、`scale` 大於 0 且不超過 1。
- R-002：Claude 的輸出不是合法 JSON、不符合結構，或違反 R-001 的語意規則時視為無效，自動重試一次（總共最多呼叫 Claude 2 次）；重試時把上一次的錯誤原因告訴 Claude。
- R-003：連續兩次無效時拋出企劃產生錯誤（`PlanGenerationError`），錯誤訊息說明最後一次的無效原因；Claude API 本身失敗或拒絕回應（`refusal`）時同樣拋出此錯誤。
- R-004：送給 Claude 的提示詞包含品牌語氣、賣點與資訊、角色身份錨點、每張實景照的 ID 與描述、本次主題，並要求以繁體中文輸出。
- R-005：依已核准的企劃產生每鏡的關鍵幀提示詞與影片提示詞；影片提示詞包含角色錨點、動作、場景與鏡頭運動描述，並要求保留實景背景、不產生文字。
- R-006：Claude 模型名稱、思考強度只從設定讀取；`CREATIVE_ENGINE=prompt` 時正式環境使用 PromptEngine，`fake` 時使用 S07 的假引擎。

## 驗收條件

- AC-001（對應 R-001）：Given 使用預錄的 Claude 回應 fixture 與品牌語氣為「親切台味」、含 3 張實景照的專案，When 以主題「清晨採梅體驗」產生企劃，Then 回傳 2～3 個企劃，每個企劃 3 鏡、功能依序為 `hook`、`feature`、`cta`、長度合計 12 秒、實景照都存在、擺放參數在範圍內。
- AC-002（對應 R-001）：Pydantic 結構拒絕缺少欄位、鏡頭數不為 3、功能順序錯誤；語意驗證拒絕長度合計不為 12 秒、引用不存在的實景照、擺放超出範圍、企劃數不在 2～3 之間。
- AC-003（對應 R-002）：Given Claude 第 1 次回傳無效 JSON、第 2 次回傳有效企劃，When 產生企劃，Then 成功回傳企劃，共呼叫 Claude 2 次，第 2 次的請求包含第 1 次的無效原因。
- AC-004（對應 R-002）：Given Claude 第 1 次回傳引用 `ph_99` 的企劃、第 2 次回傳有效企劃，When 產生企劃，Then 成功回傳企劃，共呼叫 Claude 2 次。
- AC-005（對應 R-003）：Given Claude 連續回傳無效 JSON，When 產生企劃，Then 拋出 `PlanGenerationError`，共呼叫 Claude 2 次；Claude 回應 `refusal` 或 API 錯誤時同樣拋出 `PlanGenerationError`。
- AC-006（對應 R-004）：When 組出送給 Claude 的提示詞，Then 包含品牌語氣「親切台味」、角色身份錨點的內容、每張實景照的 ID 與描述，並要求以繁體中文輸出。
- AC-007（對應 R-005）：Given 一個已核准的企劃，When 產生 3 鏡的生成提示詞，Then 每鏡都有非空的關鍵幀提示詞與影片提示詞，影片提示詞包含該鏡的鏡頭運動描述與角色錨點。
- AC-008（對應 R-006）：送給 Claude 的模型名稱與 effort 等於設定值；`CLAUDE_MODEL` 為空時建立 PromptEngine 失敗並說明缺少的設定；`build_services` 依 `CREATIVE_ENGINE` 選擇引擎。

## 驗收對應

| AC | 場景 |
|---|---|
| AC-001 | S10-01 |
| AC-002 | S10-01 |
| AC-003 | S10-02 |
| AC-004 | S10-04 |
| AC-005 | S10-03 |
| AC-006 | S10-05 |
| AC-007 | S10-06 |
| AC-008 | S10-05 |

AC-002、AC-008 以單元測試驗證（見 design.md）。

## 非功能需求

- 閘門內的測試不呼叫真實 API、不產生費用；真實呼叫只在 `@external` 測試，且需使用者同意。
- API 金鑰只從環境變數讀取，不寫入提示詞、日誌、fixture 或錯誤訊息。
- Claude 的輸出視為不受信任的資料，一律經過結構與語意驗證後才保存。

## 假設、風險與待決事項

1. **預設模型建議 `claude-opus-5-5`。** 程式不寫死模型，`.env.example` 的 `CLAUDE_MODEL` 建議填 `claude-opus-5-5`（目前預設的 Claude 模型），`CLAUDE_EFFORT` 預設 `medium`。若你想用較便宜的 `claude-sonnet-5-5`，只要改設定。
2. **拒絕回應時的備援（預設開啟）。** Claude Opus 5.5 可能因安全分類器回傳 `refusal`；草稿預設啟用伺服器端備援（`fallbacks: "default"`，beta `server-side-fallback-2026-07-01`），由 API 自動改用其他模型完成；設定 `CLAUDE_REFUSAL_FALLBACK=false` 可關閉。仍然拒絕時拋出 `PlanGenerationError`。
3. **使用結構化輸出，但仍自行驗證。** 真實呼叫以 `output_config.format`（JSON Schema）要求 Claude 輸出結構化 JSON，降低格式錯誤；但語意規則（實景照存在、合計 12 秒）無法用 Schema 表達，且 fixture 需要模擬無效輸出，因此 PromptEngine 一律自行解析與驗證。
4. **企劃 Schema 新增英文欄位。** S00 發現影片提示詞以英文描述效果較好，因此每鏡除了繁中的 `action`、`camera`，另要求 `action_en`、`camera_en`，並在 S07 的 `ShotDraft` 加上這兩個選填欄位（預設空字串，不影響 S07）。運鏡依 S00 結論要求寫明速度與幅度。
5. **生成提示詞以模板組成，不另外呼叫 Claude。** `build_shot_prompts` 依 S00 驗證過的模板（角色錨點＋動作＋場景＋運鏡＋保留實景背景、無文字）產生，省下一次呼叫與費用，結果可重現。
6. **fixture 為手工建立。** 「預錄回應」目前沒有真實錄製的資料；草稿依 S00 的企劃格式手工建立 fixture，並在檔頭註明。之後執行 `@external` 測試（需你同意與金鑰）時，可把真實回應另存一份作為對照。
7. **字幕長度不做硬性驗證。** 提示詞要求每句 12 字以內，但超過不視為無效（避免因小問題重試增加費用）；片尾卡與字幕排版由 S13、S14 處理。
8. **`CREATIVE_ENGINE` 預設 `prompt`。** 正式環境需要 `ANTHROPIC_API_KEY` 與 `CLAUDE_MODEL`；Demo 或 e2e 可設為 `fake`。
