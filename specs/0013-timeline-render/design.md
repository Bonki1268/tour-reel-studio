# 時間軸與影片合成：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
backend/app/render/timeline.py
├─ Output(aspect_ratio="9:16", width=1080, height=1920, fps=30, subtitle_lang="zh-TW")
├─ Style(primary_color="#C8553D", font="Noto Sans TC")
├─ VideoClip(shot_no|None, asset, source, provider|None, start, duration)
├─ SubtitleItem(text, start, end)
├─ AudioClip(asset, start=0, volume=0.3, fade_in=0.5, fade_out=1.0)
├─ Timeline(version=1, project_id, video_id, duration, output, style, tracks=[video, subtitle, audio])
│     model_validator：影片片段從 0 起連續不重疊、duration 等於最後一段結束、字幕在 0..duration 內
├─ ShotResult(shot_no, clip_key, duration, subtitle)
├─ build_timeline(*, project_id, video_id, shots, outro_key, bgm_key, style) -> Timeline
├─ set_clip_duration(timeline, index, seconds) -> Timeline   後續片段、字幕順延；回傳新物件
├─ ass_time(seconds) -> "H:MM:SS.cc"
└─ to_ass(timeline) -> str

backend/app/render/ffmpeg.py
├─ FfmpegRenderer(settings, fonts_dir=ASSETS/fonts)
│   ├─ build_timeline(video, shots, *, style, outro_key=None, bgm_key=None) -> dict   （Renderer 介面）
│   ├─ render(timeline, storage, output_key, thumb_key=None) -> None                 （Renderer 介面）
│   ├─ command(timeline, inputs, ass_path, output_path) -> list[str]                 純函式，可單元測試
│   └─ thumbnail_command(video_path, at, thumb_path) -> list[str]
├─ probe(path) -> ProbeResult(width, height, fps, duration, vcodec, acodec)
└─ RenderError(Exception)
```

### FFmpeg 指令（單次執行）

```
ffmpeg -y -i clip1 -i clip2 -i clip3 -i outro [-i bgm | -f lavfi -i anullsrc=r=48000:cl=stereo]
-filter_complex "
  [0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,
       tpad=stop_mode=clone:stop_duration=<d>,trim=duration=<d>,setpts=PTS-STARTPTS[v0]; …
  [v0][v1][v2][v3]concat=n=4:v=1:a=0[vc];
  [vc]subtitles=<ass>:fontsdir=<fonts>[vout];
  [4:a]atrim=duration=<T>,asetpts=PTS-STARTPTS,volume=0.3,afade=t=in:d=0.5,afade=t=out:st=<T-1>:d=1[aout]"
-map [vout] -map [aout] -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30
-c:a aac -b:a 128k -t <T> -movflags +faststart out.mp4
```

- 鏡頭片段的音訊一律不 map（Seedance 已關閉音訊；R-004）。
- 縮圖：`ffmpeg -ss <第一段中點> -i out.mp4 -frames:v 1 -q:v 3 thumb.jpg`。
- 執行：`asyncio.create_subprocess_exec`，逾時 `RENDER_TIMEOUT_S`；非 0 結束 → `RenderError`（訊息取 stderr 最後 20 行）。完成後以 ffprobe 檢查尺寸與長度，不符 → `RenderError`。
- 素材：依時間軸 `asset` 從 `Storage` 讀到暫存目錄（`tempfile.TemporaryDirectory`）。

### ASS

```
[Script Info] PlayResX: 1080  PlayResY: 1920  ScaledBorderAndShadow: yes
[V4+ Styles] Style: Default,Noto Sans TC,72,&H00FFFFFF,&H00FFFFFF,&H00<BGR>,&H64000000,-1,0,0,0,100,100,0,0,1,5,0,2,60,60,400,1
[Events] Dialogue: 0,<start>,<end>,Default,,0,0,0,,<text>
```

字幕文字跳脫：`\` → `\\`、`{` → `\{`、`}` → `\}`、換行 → `\N`。

### 編排串接

- `Renderer` 介面加上 `thumb_key` 參數與 `build_timeline` 的 `style`、`outro_key`、`bgm_key` 關鍵字參數；`FakeRenderer` 改為呼叫同一個 `timeline.build_timeline`，並寫出空白縮圖。
- `_render`：品牌主色取自 `BrandProfile.visual["colors"][0]`（沒有時用預設），`bgm_key` 取自設定；`render_thumb` key 寫入 `Render.thumb_key`。
- 合成失敗：第一次失敗 → `RENDER_RETRY` 後再合成；再失敗 → `RENDER_FAILED_FINAL`、發布 `render_failed`（帶錯誤摘要），不寫成品紀錄，不拋出例外給 Worker。
- `build_services`：`RENDERER=ffmpeg` 時使用 `FfmpegRenderer`。

## 資料模型／狀態轉換變更

- 無資料表變更（`videos.timeline`、`renders.thumb_key` 已存在）。狀態轉換沿用 S02 已定義的 `RENDER_RETRY`、`RENDER_FAILED_FINAL`。
- 時間軸 JSON 格式改為構想文件 §5.3 格式（`tracks` 為 video／subtitle／audio），`version: 1`。

## API 契約（request／response、錯誤碼）

無新端點。`GET /videos/{id}` 回傳的 `timeline` 改為新格式（S08 只回傳原 JSON，不檢查內容）。

## 失敗行為、安全與可觀測性

- 所有失敗以 `RenderError` 表示；暫存目錄一律清除。
- 錯誤摘要只含 FFmpeg stderr 末段，不含儲存網址或金鑰（素材以本機暫存檔路徑傳入 FFmpeg）。
- 日誌記錄合成耗時與輸出長度。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S13-01）＋Unit | `backend/tests/bdd/test_s13_render.py`、`backend/tests/unit/test_timeline.py` |
| R-002 | AC-002 | BDD（S13-02）＋Unit | 同上、`backend/tests/unit/test_ffmpeg.py` |
| R-003 | AC-003 | BDD（S13-03）＋Unit | 同上 |
| R-004 | AC-004 | BDD（S13-04）＋Unit | 同上 |
| R-005 | AC-005 | BDD（S13-05）＋Unit | 同上 |
| R-006 | AC-006 | BDD（S13-06）＋Unit | 同上、`backend/tests/unit/test_orchestrator_render.py` |
| R-007 | AC-007 | Unit | `backend/tests/unit/test_orchestrator_render.py` |

- 測試素材：`tests/render_support.py` 以 `ffmpeg -f lavfi -i testsrc=size=WxH:rate=24` 產生片段、`sine=frequency=440` 產生 BGM，存入記憶體儲存；session 範圍快取，避免重複產生。
- 實際合成的場景（S13-02、04、06）共用同一次合成結果（module 範圍 fixture）；S13-05 另合成一次。
- 平均音量：`ffmpeg -af volumedetect` 分別量測 0–0.3 秒與 6–9 秒。
- 編排測試以會失敗的假合成器驗證重試，不執行 FFmpeg。

預計單元測試（≥ 2，預計約 20）：
- `test_r001_clips_contiguous_from_zero`、`test_r001_rejects_gap_or_overlap[gap|overlap|wrong_total]`、`test_r001_subtitles_inside_shot`、`test_r001_without_outro`
- `test_r002_command_has_scale_crop_fps_codecs`、`test_r002_command_trims_and_pads_each_clip`、`test_r002_command_ignores_clip_audio`
- `test_r003_ass_time_format[…]`、`test_r003_ass_style_font_and_outline`、`test_r003_ass_escapes_text`
- `test_r004_command_bgm_volume_and_fades`、`test_r004_silent_track_without_bgm`
- `test_r005_set_clip_duration_shifts_following`、`test_r005_set_clip_duration_rejects_non_positive`
- `test_r006_render_record_has_thumb_key`
- `test_r007_render_retry_then_success`、`test_r007_render_fails_twice_needs_attention`

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：以單次 FFmpeg `filter_complex` 合成（縮放裁切 → 串接 → 燒錄 ASS → 混 BGM），時間軸 JSON 採構想文件 §5.3 格式並以 Pydantic 驗證；字型隨 repo 提供。
- 替代方案：MoviePy 等高階函式庫；先分段轉檔再 concat demuxer；使用系統字型。
- 取捨：單次執行速度快、暫存檔少，指令可單元測試；代價是 filter graph 較長。字型隨 repo 讓本機、CI 與部署輸出一致，代價是 repo 多約 6 MB。
