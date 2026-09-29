# 變更請求（Change Requests）

已核准的規格、`features/` 場景、開發計畫或閘門要修改時，依 `docx/spec-driven-development.md` §8 建立 `CR-xxxx.md`。

流程：
1. Claude Code 或使用者以 `_template.md` 建立 CR 草稿，Claude Code 完成影響分析
2. 使用者審閱，將「狀態」改為 approved 並填寫「核准者／時間」
3. 使用者在終端機執行：`python3 scripts/tdd.py unlock CR-0001 <要修改的檔案…> --minutes 30`
4. 修改檔案（此時 Claude Code 的 Edit／Write 可以修改列出的檔案）
5. 使用者執行 `python3 scripts/tdd.py lock` 恢復保護

Claude Code 不能核准 CR，也不能執行 `unlock`／`lock`（hook 會阻擋）。
