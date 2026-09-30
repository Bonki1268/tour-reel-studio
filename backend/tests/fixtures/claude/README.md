# Claude 預錄回應 fixture

**手工建立**（spec 0010 待決事項 6）：依 S00 `spikes/higgsfield/results/v4_plan.json` 的企劃格式撰寫，不是真實 API 錄製的回應。
之後執行 `@external` 測試（需使用者同意與金鑰）時，可把真實回應另存一份作為對照。

| 檔案 | 用途 |
|---|---|
| `valid_plans.json` | 3 個有效企劃（實景照 ph_01～ph_03、每個企劃合計 12 秒） |
| `invalid_json.txt` | 不是合法 JSON |
| `missing_photo.json` | 第 2 個企劃引用不存在的 `ph_99` |
| `wrong_duration.json` | 第 1 個企劃 3 鏡合計 14 秒 |
