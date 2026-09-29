#!/usr/bin/env python3
"""PreToolUse hook：防止 Claude Code 修改規格、核准紀錄、證據與閘門（spec-driven-development.md §9）。

一律保護：
  features/、scripts/tdd.py、.tdd/、.claude/hooks/、.claude/settings.json、.claude/commands/、
  docx/development-plan.md、docx/spec-driven-development.md、specs/_template/、specs/*/evidence.md
依內容保護：
  - specs/*/spec.md 狀態已是 approved／implemented／validated 時，整份保護
  - 任何檔案都不能由 Claude Code 寫入或更改核准欄位（狀態、核准者／時間、審核人、驗收者、驗收結果）；
    唯一例外是在 specs/ 或 changes/ 建立草稿時寫入「狀態：draft」「核准者／時間：TODO」
暫時解除：使用者依已核准的 CR 執行 `python3 scripts/tdd.py unlock CR-xxxx PATH...`。
阻擋與解鎖放行都記錄在 .tdd/hook.log。這是防止誤改的護欄，不是安全機制。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

ALWAYS = ["features/", "scripts/tdd.py", ".tdd/", ".claude/hooks/", ".claude/settings.json", ".claude/commands/",
          "docx/development-plan.md", "docx/spec-driven-development.md", "specs/_template/"]
SHELL_PROTECTED = ALWAYS + ["specs/", "changes/", "docx/validation/"]
EVIDENCE = re.compile(r"^specs/[^/]+/evidence\.md$")
SPEC = re.compile(r"^specs/[^/]+/spec\.md$")
APPROVED = re.compile(r"^狀態[:：][ \t]*(approved|implemented|validated)", re.M)
APPROVAL_LINE = re.compile(r"^[ \t]*(?:-[ \t]*)?(?:狀態|核准者／時間|審核人|驗收者|驗收結果)[:：].*$", re.M)
DRAFT_LINE = re.compile(r"^(?:狀態[:：][ \t]*draft|核准者／時間[:：][ \t]*TODO)[ \t]*$")
WRITE_BASH = re.compile(
    r"(?<![0-9&])>(?!&)|\btee\b|\bsed\s+-[a-zA-Z]*i|\bperl\s+-[a-zA-Z]*i|\brm\b|\bmv\b|\bcp\b|\btouch\b"
    r"|\btruncate\b|\bchmod\b|\bln\b|\bgit\s+(checkout|restore|rm|mv|stash|reset)\b|write_text|open\(")
TDD_CMD = re.compile(r"^\s*(python3?|uv run python|poetry run python)\s+scripts/tdd\.py\s+(status|show|spec|red|gate)"
                     r"(\s+S\d{2})?\s*$")
GIT_DANGER = re.compile(r"\bgit\s+push\b.*(--force|\s-f\b)|--no-verify")

data = json.load(sys.stdin)
tool = data.get("tool_name", "")
ti = data.get("tool_input") or {}
root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".").resolve()


def log(event: str, target: str) -> None:
    try:
        (root / ".tdd").mkdir(exist_ok=True)
        with (root / ".tdd" / "hook.log").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                                 "event": event, "tool": tool, "target": target[:300]}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def block(target: str, why: str) -> None:
    log("blocked", target)
    print(f"已阻擋：{target}。{why}\n規格、核准紀錄、證據與閘門只能由使用者修改。若你認為規格有誤或無法實作，"
          "請停止並向使用者說明要改哪裡、為什麼；需要時起草 changes/CR-xxxx.md 等待使用者核准。", file=sys.stderr)
    sys.exit(2)


def relpath(path_str: str) -> str | None:
    p = Path(path_str)
    p = (p if p.is_absolute() else root / p).resolve()
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return None


def unlocked(rel: str) -> bool:
    try:
        u = json.loads((root / ".tdd" / "unlock.json").read_text(encoding="utf-8"))
        if dt.datetime.fromisoformat(u["until"]) < dt.datetime.now().astimezone():
            return False
        return any(rel == p.strip("/") or rel.startswith(p.rstrip("/") + "/") for p in u["paths"])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def approval_lines(text: str) -> list[str]:
    return [m.group(0).strip().lstrip("-").strip() for m in APPROVAL_LINE.finditer(text)]


def new_content(old: str) -> str | None:
    if tool == "Write":
        return ti.get("content", "")
    if tool == "Edit":
        edits = [ti]
    elif tool == "MultiEdit":
        edits = ti.get("edits") or []
    else:
        return None
    text = old
    for e in edits:
        o, n = e.get("old_string", ""), e.get("new_string", "")
        text = text.replace(o, n) if e.get("replace_all") else text.replace(o, n, 1)
    return text


def check_file(target: str) -> None:
    rel = relpath(target)
    if rel is None:
        return
    if unlocked(rel):
        log("allowed-by-cr", rel)
        return
    if any(rel == x.rstrip("/") or rel.startswith(x) for x in ALWAYS) or EVIDENCE.match(rel):
        block(rel, "這是受保護的規格／證據／閘門檔案。")
    path = root / rel
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    if SPEC.match(rel) and APPROVED.search(old):
        block(rel, "這份規格已核准，修改必須走變更請求（CR）。")
    new = new_content(old)
    if new is None:
        return
    before, after = approval_lines(old), approval_lines(new)
    added = [ln for ln in after if ln not in before]
    removed = [ln for ln in before if ln not in after]
    if added or removed:
        draft_ok = (SPEC.match(rel) or rel.startswith("changes/")) and not removed \
            and all(DRAFT_LINE.match(ln) for ln in added)
        if not draft_ok:
            block(rel, "不能寫入或更改核准相關欄位（狀態、核准者、審核人、驗收者）。")


if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
    target = ti.get("file_path") or ti.get("notebook_path") or ""
    if target:
        check_file(target)
elif tool == "Bash":
    command = ti.get("command", "")
    if TDD_CMD.match(command):
        sys.exit(0)
    if re.search(r"scripts/tdd\.py\s+(unlock|lock)\b", command):
        block("tdd.py unlock／lock", "解除保護只能由使用者在終端機執行。")
    if GIT_DANGER.search(command):
        block("git 指令", "不允許 force push 或略過 git hooks。")
    if WRITE_BASH.search(command) and any(x.rstrip("/") in command for x in SHELL_PROTECTED):
        block("這個 shell 指令", "受保護的檔案不能用 shell 修改；一般檔案請改用 Edit／Write 工具。")
sys.exit(0)
