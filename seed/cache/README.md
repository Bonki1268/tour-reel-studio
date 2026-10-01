# 官網擷取快取

種子腳本只讀這裡的 `firecrawl-<domain>.json`（domain 取自 `seed/demo/demo.json` 的 `website`，去掉 `www.`），現場不連網。

```json
{
  "fetched_at": "2026-10-01T00:00:00+00:00",
  "source": "firecrawl",
  "branding": {
    "colors": {"primary": "#8B2E1F", "secondary": "#F2E3C6", "accent": "#C9A227"},
    "fonts": [{"family": "Noto Serif TC"}],
    "images": {"logo": "https://example.com/logo.svg"}
  },
  "metadata": {"booking_url": "https://example.com/booking"}
}
```

- 手寫的快取把 `source` 設為 `manual`。
- `demo.json` 有明確值（主色、訂位網址）時優先，快取只補上缺少的欄位。
- 更新快取：`python -m app.seed.run --refresh-firecrawl`（需要 `FIRECRAWL_API_KEY`，會產生費用）。失敗時保留舊快取。
- 目前的 Demo 店家沒有官網，所以還沒有快取檔。
