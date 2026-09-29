#!/usr/bin/env python3
"""Tour Reel Studio — 規格驅動（SDD）＋ BDD／TDD 步驟閘門。

每個步驟依序通過：
  spec  規格草稿結構檢查（R／AC 完整、AC 與場景雙向對應）
  red   規格已由使用者核准；已先寫好全部場景與單元測試，且執行後確實失敗 → 本機 commit
  gate  lint、S01～目前步驟的回歸測試、場景覆蓋、單元測試數、報告 → 寫入 evidence → commit 並 push
通過 gate 後，步驟才標記為完成並前進到下一步。

用法：
  python3 scripts/tdd.py status                顯示進度與下一個動作
  python3 scripts/tdd.py show  [STEP]          顯示步驟說明、規格狀態與場景
  python3 scripts/tdd.py spec  [STEP]          檢查規格結構（草稿也可檢查）
  python3 scripts/tdd.py red   [STEP]          記錄紅燈
  python3 scripts/tdd.py gate  [STEP]          執行閘門
  python3 scripts/tdd.py unlock CR-0001 PATH... [--minutes 30]   （僅供使用者）依已核准的 CR 暫時解除保護
  python3 scripts/tdd.py lock                  （僅供使用者）立即恢復保護
STEP 省略時為目前步驟。只使用 Python 標準函式庫。

環境變數：
  TRS_PYTEST (python -m pytest)   TRS_RUFF (python -m ruff check .)
  TRS_VITEST (npx vitest run)     TRS_BDDGEN (npx bddgen)   TRS_PLAYWRIGHT (npx playwright test)
  TRS_WEB_LINT (npm run --if-present lint)   TRS_WEB_TYPECHECK (npx tsc --noEmit)
  TRS_SKIP_COMPOSE=1  不自動啟動 infra/docker-compose.test.yml
  TRS_NO_GIT=1        不自動 commit／push      TRS_NO_PUSH=1  只 commit 不 push
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TDD = ROOT / ".tdd"
STATE = TDD / "progress.json"
LOGS = TDD / "logs"
UNLOCK = TDD / "unlock.json"
FEATURES = ROOT / "features"
BACKEND = ROOT / "backend"
WEB = ROOT / "apps" / "web"
CHANGES = ROOT / "changes"
PLAN = ROOT / "docx" / "development-plan.md"
COMPOSE_TEST = ROOT / "infra" / "docker-compose.test.yml"

SCENARIO_ID = re.compile(r"^(S\d{2}-\d{2})\b")
SCENARIO_HEADS = ("Scenario", "Scenario Outline", "Scenario Template", "Example")
RESET_TAG_HEADS = ("Background", "Rule", "Examples", "Scenarios")
APPROVED_STATES = ("approved", "implemented", "validated")
SECRET_FILE = re.compile(r"(^|/)\.env(\.(?!example$)[^/]*)?$|\.(pem|key|p12|pfx)$")
SECRET_TEXT = re.compile(
    r"sk-ant-[A-Za-z0-9_\-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|(?i:(api[_-]?key|secret|token)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{24,})")


# ---------- 共用 ----------

def die(msg: str) -> None:
    print(f"\n✗ {msg}", file=sys.stderr)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"✓ {msg}")


def info(msg: str) -> None:
    print(f"· {msg}")


def warn(msg: str) -> None:
    print(f"! {msg}")


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_state(st: dict) -> None:
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_step(st: dict, sid: str) -> tuple[int, dict]:
    for i, s in enumerate(st["steps"]):
        if s["id"] == sid:
            return i, s
    die(f"未知的步驟：{sid}")
    raise AssertionError


def steps_upto(st: dict, sid: str) -> list[dict]:
    i, _ = find_step(st, sid)
    return st["steps"][: i + 1]


def require_current(st: dict, sid: str) -> None:
    cur = st.get("current")
    if cur is None:
        die("所有步驟都已完成。")
    if sid != cur:
        die(f"目前步驟是 {cur}，不能對 {sid} 執行。步驟必須依序完成。")


def norm(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.lower())


def mentions(scenario_id: str, test_name: str) -> bool:
    return re.search(norm(scenario_id) + r"(?!\d)", norm(test_name)) is not None


def looks_like_scenario(test_name: str) -> bool:
    return re.search(r"s\d{4}(?!\d)", norm(test_name)) is not None


def cmd(env_name: str, default: str) -> list[str]:
    return shlex.split(os.environ.get(env_name, default))


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def run(argv: list[str], cwd: Path, log: Path | None = None, env: dict | None = None,
        timeout: int | None = None, quiet: bool = False) -> subprocess.CompletedProcess:
    if not quiet:
        where = "." if cwd == ROOT else rel(cwd)
        info(f"$ {' '.join(argv)}   (於 {where})")
    full_env = os.environ.copy()
    full_env.update(env or {})
    try:
        p = subprocess.run(argv, cwd=cwd, env=full_env, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        die(f"找不到指令：{argv[0]}")
        raise
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"逾時（{timeout} 秒）")
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(p.stdout + "\n--- stderr ---\n" + p.stderr, encoding="utf-8")
    return p


# ---------- BDD 場景（features/） ----------

def parse_features() -> list[dict]:
    """解析 features/ 下所有 .feature，回傳每個場景的 id、標題、標籤、測試套件與檔案。"""
    scenarios: list[dict] = []
    for f in sorted(FEATURES.rglob("*.feature")):
        suite = "e2e" if f.relative_to(FEATURES).parts[0] == "web" else "py"
        feature_tags: set[str] = set()
        pending: set[str] = set()
        for raw in f.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("@"):
                pending |= {t for t in line.split() if t.startswith("@")}
                continue
            head = line.split(":", 1)[0].strip()
            if head == "Feature":
                feature_tags, pending = pending, set()
            elif head in SCENARIO_HEADS:
                title = line.split(":", 1)[1].strip()
                m = SCENARIO_ID.match(title)
                if not m:
                    die(f"{rel(f)}：場景缺少編號（格式 SNN-NN）：{title}")
                tags = feature_tags | pending
                step = m.group(1)[:3]
                if f"@{step}" not in tags:
                    die(f"{rel(f)}：場景 {m.group(1)} 缺少對應的步驟標籤 @{step}")
                scenarios.append({
                    "id": m.group(1), "title": title, "tags": sorted(tags), "step": step,
                    "suite": suite, "external": "@external" in tags, "file": rel(f),
                })
                pending = set()
            elif head in RESET_TAG_HEADS:
                pending = set()
    ids = [s["id"] for s in scenarios]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        die(f"場景編號重複：{', '.join(sorted(dup))}")
    return scenarios


# ---------- 規格（specs/） ----------

def field(text: str, name: str) -> str:
    m = re.search(rf"^{re.escape(name)}[:：][ \t]*(.*)$", text, re.M)
    return m.group(1).strip() if m else ""


def section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def read_spec(step: dict) -> dict:
    """讀取並解析步驟對應的 spec.md。"""
    d = ROOT / step["spec"]
    f = d / "spec.md"
    if not f.exists():
        die(f"找不到 {rel(f)}。先依 specs/_template/ 建立規格草稿（spec.md、design.md、tasks.md），"
            "再請使用者核准。")
    text = f.read_text(encoding="utf-8")
    reqs = re.findall(r"^\s*-\s*(R-\d{3})\s*[:：]", section(text, "需求"), re.M)
    acs = {}
    for m in re.finditer(r"^\s*-\s*(AC-\d{3})\s*[（(]\s*對應\s*([^）)]*)[）)]", section(text, "驗收條件"), re.M):
        acs[m.group(1)] = re.findall(r"R-\d{3}", m.group(2))
    mapping: dict[str, list[str]] = {}
    for line in section(text, "驗收對應").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and re.fullmatch(r"AC-\d{3}", cells[0]):
            mapping[cells[0]] = re.findall(r"S\d{2}-\d{2}", cells[1])
    return {
        "dir": d, "file": f, "text": text,
        "status": field(text, "狀態").split()[0].lower() if field(text, "狀態") else "",
        "version": field(text, "版本"), "approver": field(text, "核准者／時間"),
        "linked": field(text, "關聯開發步驟"), "reqs": reqs, "acs": acs, "mapping": mapping,
    }


def check_spec(step: dict, require: tuple[str, ...] | None) -> dict:
    """檢查規格結構；require 為允許的狀態（None 表示不檢查狀態，用於草稿自檢）。"""
    sp = read_spec(step)
    sid = step["id"]
    scen = {s["id"]: s for s in parse_features() if s["step"] == sid}
    active = {i for i, s in scen.items() if not s["external"]}
    errs = []
    if sid not in sp["linked"]:
        errs.append(f"「關聯開發步驟」應包含 {sid}")
    if not sp["reqs"]:
        errs.append("「## 需求」沒有任何 R-xxx（格式：- R-001：…）")
    if not sp["acs"]:
        errs.append("「## 驗收條件」沒有任何 AC-xxx（格式：- AC-001（對應 R-001）：…）")
    for r in sp["reqs"]:
        if not any(r in refs for refs in sp["acs"].values()):
            errs.append(f"{r} 沒有任何驗收條件")
    for ac, refs in sp["acs"].items():
        if not refs:
            errs.append(f"{ac} 沒有對應需求")
        for r in refs:
            if r not in sp["reqs"]:
                errs.append(f"{ac} 對應到未定義的 {r}")
        if ac not in sp["mapping"] or not sp["mapping"][ac]:
            errs.append(f"{ac} 沒有列在「## 驗收對應」或沒有對應場景")
    for ac, ids in sp["mapping"].items():
        if ac not in sp["acs"]:
            errs.append(f"「## 驗收對應」中的 {ac} 未在驗收條件中定義")
        for i in ids:
            if i not in scen:
                errs.append(f"{ac} 對應的場景 {i} 不存在或不屬於 {sid}")
    mapped = {i for ids in sp["mapping"].values() for i in ids}
    for i in sorted(active - mapped):
        errs.append(f"場景 {i} 沒有被任何 AC 對應（規格未涵蓋此行為）")
    for name in ("design.md", "tasks.md"):
        p = sp["dir"] / name
        if not p.exists() or len(p.read_text(encoding="utf-8").strip()) < 80:
            errs.append(f"缺少或內容過少：{rel(p)}")
    if require is not None:
        if sp["status"] not in require:
            errs.append(f"規格狀態為「{sp['status'] or '未填'}」，需要 {' / '.join(require)}（由使用者核准）")
        if not sp["approver"] or "TODO" in sp["approver"]:
            errs.append("「核准者／時間」尚未由使用者填寫")
    if errs:
        die(f"{rel(sp['file'])} 未通過規格檢查：\n  " + "\n  ".join(errs))
    return sp


def set_spec_status(sp: dict, status: str) -> None:
    text = re.sub(r"^(狀態[:：][ \t]*)\S+", rf"\g<1>{status}", sp["text"], count=1, flags=re.M)
    sp["file"].write_text(text, encoding="utf-8")


def append_evidence(step: dict, sp: dict, stats: dict, st: dict) -> Path:
    ev = sp["dir"] / "evidence.md"
    if not ev.exists():
        ev.write_text(
            f"# 驗收證據：{sp['dir'].name}\n\n"
            "> 「閘門紀錄」由 scripts/tdd.py 自動寫入；「人工驗收」由使用者填寫。Claude Code 不得修改本檔。\n\n"
            "## 人工驗收\n\n- 驗收者：TODO\n- 驗收結果：TODO\n- 已知限制：TODO\n\n## 閘門紀錄\n",
            encoding="utf-8")
    red = json.loads((LOGS / f"{step['id']}-red.json").read_text(encoding="utf-8"))
    rows = "\n".join(f"| {ac} | {', '.join(ids)} | 通過 |" for ac, ids in sp["mapping"].items())
    entry = (
        f"\n### {now()}　{step['id']} 閘門通過\n\n"
        f"- 規格版本：{sp['version'] or '未標示'}\n"
        f"- 紅燈：{red['at']}，{red['total']} 個測試中 {red['failed']} 個失敗\n"
        f"- 回歸範圍：{st['steps'][1]['id']}–{step['id']}，測試 {stats['tests']} 個全數通過，"
        f"場景 {stats['scenarios']} 個皆有通過的測試\n"
        f"- 本步驟單元測試：{stats['unit_tests']} 個\n"
        f"- 測試指令：`python3 scripts/tdd.py gate {step['id']}`（原始結果見 .tdd/logs/{step['id']}-gate-*.xml）\n\n"
        f"| AC | 場景 | 結果 |\n|---|---|---|\n{rows}\n"
    )
    with ev.open("a", encoding="utf-8") as fh:
        fh.write(entry)
    return ev


# ---------- 測試執行 ----------

def parse_junit(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    cases = []
    for tc in ET.parse(path).getroot().iter("testcase"):
        if tc.find("failure") is not None or tc.find("error") is not None:
            status = "failed"
        elif tc.find("skipped") is not None:
            status = "skipped"
        else:
            status = "passed"
        cases.append({"name": f'{tc.get("classname", "")}::{tc.get("name", "")}', "status": status})
    return cases


def compose_up() -> None:
    if COMPOSE_TEST.exists() and os.environ.get("TRS_SKIP_COMPOSE") != "1":
        p = run(["docker", "compose", "-f", str(COMPOSE_TEST), "up", "-d", "--wait"], ROOT, LOGS / "compose.log")
        if p.returncode:
            die("無法啟動測試用 docker compose（見 .tdd/logs/compose.log）")


def run_py(expr: str, tag: str) -> tuple[int, list[dict] | None]:
    if not (BACKEND / "pyproject.toml").exists():
        die("找不到 backend/pyproject.toml。S01 需要先建立後端骨架與測試設定。")
    out = LOGS / f"{tag}-py.xml"
    out.unlink(missing_ok=True)
    p = run(cmd("TRS_PYTEST", "python -m pytest")
            + ["-m", expr, f"--junitxml={out}", "-p", "no:cacheprovider", "-q"],
            BACKEND, LOGS / f"{tag}-py.log")
    return p.returncode, parse_junit(out)


def collect_py(expr: str) -> tuple[int, list[str]]:
    p = run(cmd("TRS_PYTEST", "python -m pytest")
            + ["--collect-only", "-q", "-m", expr, "-p", "no:cacheprovider"], BACKEND)
    return p.returncode, [ln.strip() for ln in p.stdout.splitlines() if "::" in ln]


def run_vitest(tag: str, step: str | None = None) -> tuple[int, list[dict] | None]:
    if not (WEB / "package.json").exists():
        die("找不到 apps/web/package.json。S15 需要先建立前端專案。")
    out = LOGS / f"{tag}-web.xml"
    out.unlink(missing_ok=True)
    argv = cmd("TRS_VITEST", "npx vitest run") + ["--reporter=junit", f"--outputFile={out}"]
    if step:
        argv += ["-t", rf"\[{step}\]"]
    p = run(argv, WEB, LOGS / f"{tag}-web.log")
    return p.returncode, parse_junit(out)


def run_e2e(tag: str, grep: str) -> tuple[int, list[dict] | None]:
    if not (WEB / "package.json").exists():
        die("找不到 apps/web/package.json。S15 需要先建立前端專案。")
    gen = run(cmd("TRS_BDDGEN", "npx bddgen"), WEB, LOGS / f"{tag}-bddgen.log")
    if gen.returncode:
        die(f"bddgen 失敗，通常是場景缺少步驟定義（見 .tdd/logs/{tag}-bddgen.log）")
    out = LOGS / f"{tag}-e2e.xml"
    out.unlink(missing_ok=True)
    p = run(cmd("TRS_PLAYWRIGHT", "npx playwright test")
            + ["--reporter=junit", "--grep", grep, "--grep-invert", "@external"],
            WEB, LOGS / f"{tag}-e2e.log", env={"PLAYWRIGHT_JUNIT_OUTPUT_NAME": str(out)})
    return p.returncode, parse_junit(out)


def lint() -> None:
    if (BACKEND / "pyproject.toml").exists():
        if run(cmd("TRS_RUFF", "python -m ruff check ."), BACKEND, LOGS / "lint-py.log").returncode:
            die("ruff 檢查未通過（見 .tdd/logs/lint-py.log）")
        ok("後端 lint 通過")
    if (WEB / "package.json").exists():
        if run(cmd("TRS_WEB_LINT", "npm run --if-present lint"), WEB, LOGS / "lint-web.log").returncode:
            die("前端 lint 未通過（見 .tdd/logs/lint-web.log）")
        if (WEB / "tsconfig.json").exists():
            if run(cmd("TRS_WEB_TYPECHECK", "npx tsc --noEmit"), WEB, LOGS / "typecheck-web.log").returncode:
                die("前端型別檢查未通過（見 .tdd/logs/typecheck-web.log）")
        ok("前端 lint 與型別檢查通過")


def check_reports(step: dict) -> None:
    for rep in step.get("reports", []):
        path = ROOT / rep["path"]
        if not path.exists():
            die(f"找不到報告 {rep['path']}")
        text = path.read_text(encoding="utf-8")
        if "TODO" in text:
            die(f"{rep['path']} 仍有 TODO 未填寫")
        for name in rep["fields"]:
            if not re.search(rf"^- {re.escape(name)}[:：][ \t]*\S", text, re.M):
                die(f"{rep['path']} 缺少欄位「{name}」的值")
        ok(f"報告 {rep['path']} 已填寫完整")


# ---------- Git ----------

def git(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    # 不讓 git 等待輸入帳密；未設定認證時直接失敗並回報
    return run(["git", *args], ROOT, timeout=timeout, quiet=True,
               env={"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"})


def git_commit(title: str, body: str, push: bool) -> dict:
    """commit 所有變更（先掃描機密）；push=True 時推送到遠端。失敗只警告，不影響閘門結果。"""
    result = {"commit": None, "pushed": False}
    if os.environ.get("TRS_NO_GIT") == "1":
        info("TRS_NO_GIT=1，略過 commit／push")
        return result
    if shutil.which("git") is None:
        warn("找不到 git，未 commit")
        return result
    if not (ROOT / ".git").exists():
        if git("init", "-b", "main").returncode:
            warn("git init 失敗，未 commit")
            return result
        ok("已初始化 git repository（分支 main）")
    git("add", "-A")
    staged = [f for f in git("diff", "--cached", "--name-only").stdout.splitlines() if f]
    bad_files = [f for f in staged if SECRET_FILE.search(f)]
    diff = git("diff", "--cached", "-U0", timeout=120).stdout
    bad_text = sorted({m.group(0)[:12] + "…" for m in SECRET_TEXT.finditer(diff)})
    if bad_files or bad_text:
        git("reset", "-q")
        warn("偵測到可能的機密資料，已取消 commit：\n    " + "\n    ".join(bad_files + bad_text)
             + "\n  請移除或加入 .gitignore 後重新執行 gate。")
        return result
    if staged:
        p = git("commit", "-q", "-m", title, "-m", body)
        if p.returncode:
            warn("commit 失敗（可能尚未設定 git user.name／user.email）：" + (p.stderr or p.stdout).strip()[:300])
            return result
    result["commit"] = git("rev-parse", "--short", "HEAD").stdout.strip() or None
    if staged:
        ok(f"已 commit {result['commit']}：{title}")
    else:
        info("沒有新的變更需要 commit")
    if not push or os.environ.get("TRS_NO_PUSH") == "1":
        return result
    if not git("remote").stdout.split():
        warn("尚未設定遠端，未 push。設定方式：git remote add origin <你的 GitHub repo 網址>")
        return result
    has_upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode == 0
    p = git("push", "-q") if has_upstream else git("push", "-q", "-u", "origin", "HEAD", timeout=120)
    if p.returncode:
        warn("push 失敗，commit 已保留在本機。若是認證問題，請先執行 gh auth login（或手動 git push 一次讓鑰匙圈記住登入），"
             "再執行 git push：" + (p.stderr or p.stdout).strip()[:300])
    else:
        result["pushed"] = True
        ok("已 push 到遠端")
    return result


# ---------- 指令 ----------

def cmd_status(st: dict) -> None:
    cur = st.get("current")
    for s in st["steps"]:
        mark = "✓" if s.get("status") == "done" else ("▶" if s["id"] == cur else " ")
        suites = ",".join(s["suites"]) or "報告"
        print(f" {mark} {s['id']}  {s['title']}  [{s['milestone']}｜{suites}]")
    if not cur:
        print("\n所有步驟都已完成。")
        return
    _, s = find_step(st, cur)
    if s.get("type") == "spike":
        nxt = f"使用者完成 {s['reports'][0]['path']} 後執行 python3 scripts/tdd.py gate"
    else:
        spec_file = ROOT / s["spec"] / "spec.md"
        status = read_spec(s)["status"] if spec_file.exists() else ""
        if status not in APPROVED_STATES:
            nxt = (f"撰寫或修訂規格草稿 {s['spec']}/（spec.md、design.md、tasks.md），執行 "
                   "python3 scripts/tdd.py spec 自檢，然後停下來請使用者核准")
        elif not s.get("red_at"):
            nxt = "撰寫本步驟所有場景的步驟定義與單元測試（含最小骨架），然後執行 python3 scripts/tdd.py red"
        else:
            nxt = "實作並重構到測試全數通過，然後執行 python3 scripts/tdd.py gate"
    print(f"\n目前步驟：{cur} {s['title']}\n下一個動作：{nxt}")


def cmd_show(st: dict, sid: str) -> None:
    _, step = find_step(st, sid)
    if PLAN.exists():
        text = PLAN.read_text(encoding="utf-8")
        m = re.search(rf"^### {sid}\b.*?(?=^### S\d{{2}}\b|^## |\Z)", text, re.M | re.S)
        print(m.group(0).rstrip() if m else f"（development-plan.md 中找不到 ### {sid}）")
    if step.get("spec"):
        spec_file = ROOT / step["spec"] / "spec.md"
        status = read_spec(step)["status"] if spec_file.exists() else "尚未建立"
        print(f"\n規格：{step['spec']}/spec.md（狀態：{status}）")
    scen = [s for s in parse_features() if s["step"] == sid]
    if scen:
        print(f"\n驗收場景（{len(scen)}）：")
        for s in scen:
            ext = "  [external，不列入閘門]" if s["external"] else ""
            print(f"  {s['id']}  {s['title'][7:]}  ← {s['file']}{ext}")
    print(f"\n最少單元測試數：{step.get('min_unit', 0)}；測試套件：{', '.join(step['suites']) or '報告'}")


def cmd_spec(st: dict, sid: str) -> None:
    _, step = find_step(st, sid)
    if not step.get("spec"):
        die(f"{sid} 沒有對應的 spec package。")
    sp = check_spec(step, None)
    ok(f"{rel(sp['file'])} 結構正確：需求 {len(sp['reqs'])} 項、驗收條件 {len(sp['acs'])} 項，"
       f"場景全部被對應。目前狀態：{sp['status'] or '未填'}")
    if sp["status"] not in APPROVED_STATES:
        print("下一步：停下來，請使用者審閱並將「狀態」改為 approved、填寫「核准者／時間」。")


def count_units(sid: str, suites: list[str], web_cases: list[dict] | None) -> int:
    n = 0
    if "py" in suites:
        rc, ids = collect_py(f"{sid} and not external")
        if rc not in (0, 5):
            die(f"pytest 收集 {sid} 測試失敗（exit {rc}）")
        n += sum(1 for i in ids if not looks_like_scenario(i))
    if "web" in suites and web_cases:
        n += sum(1 for c in web_cases if f"[{sid}]" in c["name"] and not looks_like_scenario(c["name"]))
    return n


def cmd_red(st: dict, sid: str) -> None:
    require_current(st, sid)
    _, step = find_step(st, sid)
    if step.get("type") == "spike":
        die(f"{sid} 是技術驗證步驟，沒有紅燈階段；使用者填完報告後直接執行 gate。")
    sp = check_spec(step, APPROVED_STATES)
    ok(f"規格 {rel(sp['file'])} 已核准（{sp['version'] or '未標示版本'}，{sp['approver']}）")
    LOGS.mkdir(parents=True, exist_ok=True)
    scen = [s for s in parse_features() if s["step"] == sid and not s["external"]]
    results: dict[str, list[dict]] = {}
    tag = f"{sid}-red"

    if "py" in step["suites"]:
        compose_up()
        rc, cases = run_py(f"{sid} and not external", tag)
        if cases is None or rc not in (0, 1):
            die(f"pytest 執行異常（exit {rc}）。收集或匯入錯誤不算紅燈：請先建立拋出 NotImplementedError 的最小骨架，"
                f"讓測試能被收集後再失敗。見 .tdd/logs/{tag}-py.log")
        if not cases:
            die(f"沒有任何標記為 {sid} 的 pytest 測試。")
        results["py"] = cases
    if "web" in step["suites"]:
        rc, cases = run_vitest(tag, sid)
        if cases is None or rc not in (0, 1):
            die(f"vitest 執行異常（exit {rc}），見 .tdd/logs/{tag}-web.log")
        active = [c for c in cases if c["status"] != "skipped"]
        if not active:
            die(f"沒有任何名稱含 [{sid}] 的 vitest 測試。")
        results["web"] = active
    if "e2e" in step["suites"]:
        rc, cases = run_e2e(tag, f"@{sid}")
        if cases is None or rc not in (0, 1):
            die(f"Playwright 執行異常（exit {rc}），見 .tdd/logs/{tag}-e2e.log")
        results["e2e"] = cases

    missing = [s["id"] for s in scen
               if not any(mentions(s["id"], c["name"]) for c in results.get(s["suite"], []))]
    if missing:
        die(f"以下場景還沒有對應的測試：{', '.join(missing)}。紅燈前必須寫好本步驟全部場景的步驟定義。")

    units = count_units(sid, step["suites"], results.get("web"))
    if units < step.get("min_unit", 0):
        die(f"{sid} 只有 {units} 個單元測試，至少需要 {step['min_unit']} 個。")

    all_cases = [c for cs in results.values() for c in cs]
    failed = [c["name"] for c in all_cases if c["status"] == "failed"]
    if not failed:
        die("測試全部通過，這不是紅燈。請確認測試真的在驗證尚未實作的行為。")

    summary = {"step": sid, "at": now(), "total": len(all_cases), "failed": len(failed),
               "unit_tests": units, "spec_version": sp["version"], "failed_tests": failed[:50]}
    (LOGS / f"{sid}-red.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    step["red_at"] = summary["at"]
    save_state(st)
    ok(f"紅燈已記錄：{len(all_cases)} 個測試中 {len(failed)} 個失敗，單元測試 {units} 個。")
    git_commit(f"test({sid}): 紅燈 — {step['title']}",
               f"規格：{step['spec']} {sp['version']}\n失敗 {len(failed)}/{len(all_cases)}，單元測試 {units} 個",
               push=False)
    print("下一步：實作最少的程式碼讓測試通過，重構後執行 python3 scripts/tdd.py gate")


def cmd_gate(st: dict, sid: str) -> None:
    require_current(st, sid)
    idx, step = find_step(st, sid)
    LOGS.mkdir(parents=True, exist_ok=True)

    if step.get("type") == "spike":
        check_reports(step)
        return advance(st, idx, {"type": "spike"}, None)

    sp = check_spec(step, APPROVED_STATES)
    if not step.get("red_at") or not (LOGS / f"{sid}-red.json").exists():
        die(f"{sid} 尚未記錄紅燈。先寫測試並執行 python3 scripts/tdd.py red")

    upto = steps_upto(st, sid)
    ids_by_suite = {k: [s["id"] for s in upto if k in s["suites"]] for k in ("py", "web", "e2e")}
    scen = [s for s in parse_features() if s["step"] in {x["id"] for x in upto} and not s["external"]]
    results: dict[str, list[dict]] = {}
    tag = f"{sid}-gate"

    lint()

    if ids_by_suite["py"]:
        compose_up()
        expr = f"({' or '.join(ids_by_suite['py'])}) and not external"
        rc, cases = run_py(expr, tag)
        if cases is None:
            die(f"pytest 沒有產生結果（exit {rc}），見 .tdd/logs/{tag}-py.log")
        results["py"] = cases
        every = " or ".join(s["id"] for s in st["steps"])
        rc_u, untagged = collect_py(f"not ({every})")
        if rc_u == 0 and untagged:
            die("以下測試沒有步驟標記（pytest.mark.SNN）：\n  " + "\n  ".join(untagged[:20]))
    if ids_by_suite["web"]:
        rc, cases = run_vitest(tag)
        if cases is None:
            die(f"vitest 沒有產生結果（exit {rc}），見 .tdd/logs/{tag}-web.log")
        results["web"] = cases
    if ids_by_suite["e2e"]:
        rc, cases = run_e2e(tag, "|".join(f"@{i}" for i in ids_by_suite["e2e"]))
        if cases is None:
            die(f"Playwright 沒有產生結果（exit {rc}），見 .tdd/logs/{tag}-e2e.log")
        results["e2e"] = cases

    problems = []
    for suite, cases in results.items():
        failed = [c["name"] for c in cases if c["status"] == "failed"]
        skipped = [c["name"] for c in cases if c["status"] == "skipped"]
        if failed:
            problems.append(f"[{suite}] {len(failed)} 個測試失敗：\n    " + "\n    ".join(failed[:15]))
        if skipped:
            problems.append(f"[{suite}] 閘門不允許略過或 xfail 的測試：\n    " + "\n    ".join(skipped[:15]))
    missing = [s["id"] for s in scen
               if not any(mentions(s["id"], c["name"]) and c["status"] == "passed"
                          for c in results.get(s["suite"], []))]
    if missing:
        problems.append("以下場景沒有通過的測試：" + ", ".join(missing))
    units = count_units(sid, step["suites"], results.get("web"))
    if units < step.get("min_unit", 0):
        problems.append(f"{sid} 只有 {units} 個單元測試，至少需要 {step['min_unit']} 個")
    if problems:
        die("閘門未通過：\n  " + "\n  ".join(problems))

    check_reports(step)
    total = sum(len(c) for c in results.values())
    ok(f"回歸測試 {total} 個全數通過（涵蓋 {upto[1]['id']}–{sid}），場景 {len(scen)} 個皆有通過的測試。")
    stats = {"tests": total, "scenarios": len(scen), "unit_tests": units}
    ev = append_evidence(step, sp, stats, st)
    if sp["status"] == "approved":
        set_spec_status(sp, "implemented")
    ok(f"已寫入 {rel(ev)}，規格狀態更新為 implemented（使用者完成人工驗收後可改為 validated）")
    advance(st, idx, stats, sp)


def advance(st: dict, idx: int, stats: dict, sp: dict | None) -> None:
    step = st["steps"][idx]
    step["status"] = "done"
    step["done_at"] = now()
    step["gate"] = stats
    nxt = st["steps"][idx + 1] if idx + 1 < len(st["steps"]) else None
    st["current"] = nxt["id"] if nxt else None
    entry = {"step": step["id"], "done_at": step["done_at"], **stats}
    st.setdefault("history", []).append(entry)
    save_state(st)
    ok(f"{step['id']} {step['title']} 通過閘門。")
    kind = "docs" if step.get("type") == "spike" else "feat"
    body = "\n".join(f"{k}: {v}" for k, v in stats.items())
    if sp:
        body += f"\nspec: {step['spec']} {sp['version']}"
    git_commit(f"{kind}({step['id']}): {step['title']}", body, push=True)
    print(f"下一步：{nxt['id']} {nxt['title']}（python3 scripts/tdd.py show）" if nxt else "所有步驟完成。")


# ---------- 規格解鎖（僅供使用者） ----------

def cmd_unlock(cr: str, paths: list[str], minutes: int) -> None:
    f = CHANGES / f"{cr}.md"
    if not re.fullmatch(r"CR-\d{4}", cr) or not f.exists():
        die(f"找不到變更請求 changes/{cr}.md")
    text = f.read_text(encoding="utf-8")
    if field(text, "狀態").lower() != "approved" or not field(text, "核准者／時間") \
            or "TODO" in field(text, "核准者／時間"):
        die(f"{cr} 尚未核准（需要「狀態：approved」與「核准者／時間」）")
    if not paths:
        die("請列出要暫時解除保護的檔案路徑")
    until = dt.datetime.now().astimezone() + dt.timedelta(minutes=minutes)
    UNLOCK.write_text(json.dumps({"cr": cr, "paths": paths, "until": until.isoformat(timespec="seconds")},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    ok(f"依 {cr} 暫時解除保護至 {until:%H:%M}：{', '.join(paths)}。完成後執行 python3 scripts/tdd.py lock")


def cmd_lock() -> None:
    UNLOCK.unlink(missing_ok=True)
    ok("已恢復保護")


def main() -> None:
    ap = argparse.ArgumentParser(description="Tour Reel Studio SDD＋BDD＋TDD 步驟閘門")
    ap.add_argument("command", choices=["status", "show", "spec", "red", "gate", "unlock", "lock"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--minutes", type=int, default=30)
    a = ap.parse_args()
    if a.command == "unlock":
        if not a.args:
            die("用法：python3 scripts/tdd.py unlock CR-0001 PATH... [--minutes 30]")
        return cmd_unlock(a.args[0], a.args[1:], a.minutes)
    if a.command == "lock":
        return cmd_lock()
    st = load_state()
    sid = a.args[0] if a.args else st.get("current")
    if a.command == "status":
        cmd_status(st)
    elif sid is None:
        die("所有步驟都已完成。")
    elif a.command == "show":
        cmd_show(st, sid)
    elif a.command == "spec":
        cmd_spec(st, sid)
    elif a.command == "red":
        cmd_red(st, sid)
    else:
        cmd_gate(st, sid)


if __name__ == "__main__":
    main()
