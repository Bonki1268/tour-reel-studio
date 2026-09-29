# S00 Higgsfield 技術驗證（一次性腳本，不受閘門管理）

模型：Seedance 2.5（`bytedance/seedance-2.5/text-to-video`、`/image-to-video`）；B1 精修用 `xai/grok-imagine-image-2.0`。

## 準備

```bash
cd spikes/higgsfield && poetry install
```

- 金鑰：repo 根目錄 `.env.local` 的 `HF_KEY=key-id:key-secret`（已被 `.gitignore` 排除；腳本不會印出）
- 輸入（`inputs/`，不進 repo）：`brand.json`（由 `brand.example.json` 複製修改）、`character_cutout.png`（去背全身圖）、可選 `identity_board.png`、`brand.json` 中指定的 3 張實景照

## 執行

每支腳本預設**只估價**（呼叫官方 `/estimate/` 端點，不產生費用）；加 `--yes` 才實際生成。

| 腳本 | 內容 |
|---|---|
| `v1_text_to_video.py` | 文字生影片 5 秒、720p、16:9 |
| `v2_b1_image_to_video.py` | B1 粗合成當首幀 vs. Grok 精修後當首幀 |
| `v3_consistency.py --mode raw\|refined` | 同一角色 3 鏡 |
| `v4_tourism_promo.py` | tourism-promo 企劃與提示詞（不呼叫 API） |

每次生成都寫入 `results/runs.jsonl`：request_id、參數、預估點數、狀態、耗時、輸出網址。`failed`／`nsfw`／`canceled`、送出錯誤與逾時一律視為失敗並以非 0 結束。

## 設計備註

- SDK 的 `subscribe` 在任何終止狀態都回傳 JSON（不拋例外），因此每次都檢查 `status == "completed"`
- SDK 預設會對 POST 的 5xx／429 重試；送出生成不支援冪等鍵，重送可能重複扣點，所以改為 POST 不重試、GET 輪詢照常重試
- 狀態回應不含點數欄位，點數以送出前的估價為準；實際扣點以 Higgsfield 控制台為準
