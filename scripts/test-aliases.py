#!/usr/bin/env python3
"""Guard the alias regexes: loosening one silently reroutes real work.

  python3 scripts/test-aliases.py   # exit 1 on drift

Add a case here whenever hit-report.py surfaces a false positive.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route as RT  # noqa: E402
from quality import (  # noqa: E402
    discard_secret_without_store,
    is_junk,
    is_thin,
    normalize_lesson,
    path_missing_auth_lifecycle,
)

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
APPEND = SCRIPTS / "append-episode.py"
DISTILL = SCRIPTS / "distill.py"
PROMOTE = SCRIPTS / "promote-playbook.py"
GOLD = REPO / "examples" / "traces" / "playbooks" / "_drafts" / "gold-stale_creds.md"

# (query, expected alias or None)
CASES = [
    ("把代码推到远端", "git-push"),
    ("推一下", "git-push"),
    ("git push origin main", "git-push"),
    ("跑一下核心回归测试", "run-tests"),
    ("run the tests", "run-tests"),
    ("跑一下检索", "retrieve"),
    ("找相似的历史路径", "retrieve"),
    ("蒸馏一下", "distill"),
    ("效率评估", "eval-loo"),
    # Describing a topic is not an imperative to run it.
    ("分析一下本地记忆效果然后是否可以开源", None),
    ("修检索漏数据和明文口令", None),
    ("pytest 的超时怎么配", None),
    ("文档里写了 git push 的流程", None),
]

JUNK = [
    {"task": "用户确认修复实测结果（ok）", "preferred_path": ["等用户确认"]},
    {"task": "系统通知：检查完成", "preferred_path": ["无"]},
    {"task": "随便问问（短问）", "preferred_path": ["答疑"]},
]
NOT_JUNK = [
    {"task": "确认分页最后除法向下取整", "preferred_path": ["改 Math.Floor"]},
    {"task": "跑核心回归测试", "preferred_path": ["python3 -m pytest tests/"]},
]

PREF_CASES = [
    ("打开浏览器看下页面", "Browser"),
    ("截图发我", "Browser"),
    ("跑一下核心回归测试", "Tests"),
    ("看下日志为什么失败", "Logs"),
    ("把代码推到远端", "Git push"),
    ("给你 token 推一下", "Git push"),
    ("蒸馏失败模式", "Distill"),
]


def _run(cmd: list[str], env: dict | None = None, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(REPO),
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def _base_ep(**kwargs) -> dict:
    ep = {
        "id": "test-ep",
        "task": "test task",
        "retrieved": [],
        "preferred_path": ["python3 scripts/test-aliases.py", "check exit 0"],
        "decisions": [],
        "outcome": {"ok": True, "tests": ""},
        "critique": [],
    }
    ep.update(kwargs)
    return ep


def test_append_mode_gate(fails: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        env = {**os.environ, "LLM_TRACE_REUSE_HOME": str(home)}

        prose = _base_ep(
            id="t-prose",
            critique=[{
                "mode": "这是一段很长的散文描述，说明凭证过期以后应该怎么处理才对啊",
                "better": "ask then store",
            }],
        )
        r = _run([sys.executable, str(APPEND)], env=env, input_text=json.dumps(prose, ensure_ascii=False))
        if r.returncode != 2:
            fails.append(f"append prose mode: expected exit 2, got {r.returncode}")

        unc = _base_ep(
            id="t-unc",
            critique=[{"mode": "totally_unknown_xyz", "better": "x"}],
        )
        r = _run([sys.executable, str(APPEND)], env=env, input_text=json.dumps(unc, ensure_ascii=False))
        if r.returncode != 2:
            fails.append(f"append unclassified mode: expected exit 2, got {r.returncode}")

        ok = _base_ep(
            id="t-slot",
            critique=[{"mode": "stale_creds", "cost": "loop", "better": "ask token"}],
        )
        r = _run([sys.executable, str(APPEND)], env=env, input_text=json.dumps(ok, ensure_ascii=False))
        if r.returncode != 0:
            fails.append(f"append slot name: expected 0, got {r.returncode}: {r.stderr}")

        # --force warns but writes
        r = _run(
            [sys.executable, str(APPEND), "--force"],
            env=env,
            input_text=json.dumps(prose, ensure_ascii=False),
        )
        if r.returncode != 0:
            fails.append(f"append --force prose: expected 0, got {r.returncode}: {r.stderr}")
        if "WARN" not in (r.stderr or ""):
            fails.append("append --force prose: expected WARN on stderr")
        written = list(home.glob("*.jsonl"))
        if not written:
            fails.append("append --force: nothing written to traces home")


def test_distill_drafts(fails: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        # Two episodes same non-lifecycle slot → ripe at 2; one lifecycle → ripe at 1
        day = home / "2026-01-01.jsonl"
        eps = [
            {
                "id": "ep-a",
                "task": "push after auth fail",
                "retrieved": [],
                "preferred_path": [
                    "git push origin HEAD",
                    "失败问 token",
                    "save .llm-trace-reuse/secrets/git.pat",
                    "GIT_ASKPASS retry push",
                ],
                "critique": [{"mode": "stale_creds", "cost": "keychain loop", "better": "ask then overwrite store"}],
                "outcome": {"ok": True, "tests": ""},
            },
            {
                "id": "ep-b1",
                "task": "env pin sdk",
                "retrieved": [],
                "preferred_path": ["dotnet --version", "pin global.json sdk"],
                "critique": [{"mode": "env_setup", "cost": "wrong sdk", "better": "pin global.json"}],
                "outcome": {"ok": True, "tests": ""},
            },
            {
                "id": "ep-b2",
                "task": "fix sdk mismatch",
                "retrieved": [],
                "preferred_path": ["check global.json", "dotnet build"],
                "critique": [{"mode": "env_setup", "cost": "rebuild", "better": "pin sdk in global.json"}],
                "outcome": {"ok": True, "tests": ""},
            },
            # Same episode id twice in one file should still count once for secret_hygiene
            {
                "id": "ep-sec",
                "task": "token hygiene",
                "retrieved": [],
                "preferred_path": [
                    "never put token in URL",
                    "write .llm-trace-reuse/secrets/git.pat",
                    "失败再问 token",
                ],
                "critique": [
                    {"mode": "secret_hygiene", "better": "store locally"},
                    {"mode": "secret_hygiene", "better": "store locally again"},
                ],
                "outcome": {"ok": True, "tests": ""},
            },
        ]
        day.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in eps), encoding="utf-8")

        r = _run([sys.executable, str(DISTILL), str(home)])
        if r.returncode != 0:
            fails.append(f"distill exit {r.returncode}: {r.stderr}")
            return
        try:
            summary = json.loads(r.stdout)
        except json.JSONDecodeError:
            fails.append(f"distill stdout not JSON: {r.stdout[:200]!r}")
            return

        by_slot = {row["slot"]: row for row in summary.get("distill") or []}
        if by_slot.get("stale_creds", {}).get("count") != 1:
            fails.append(f"distill stale_creds count want 1: {by_slot.get('stale_creds')}")
        if by_slot.get("secret_hygiene", {}).get("count") != 1:
            fails.append(
                f"distill per-episode counting: secret_hygiene want 1, got {by_slot.get('secret_hygiene')}"
            )
        if by_slot.get("env_setup", {}).get("count") != 2:
            fails.append(f"distill env_setup count want 2: {by_slot.get('env_setup')}")

        drafts = summary.get("drafts_written") or []
        stale_draft = home / "playbooks" / "_drafts" / "stale_creds.md"
        if not stale_draft.is_file():
            fails.append(f"distill should write lifecycle draft at {stale_draft}; drafts={drafts}")
        elif '"status: draft"' not in stale_draft.read_text(encoding="utf-8") and "status: draft" not in stale_draft.read_text(encoding="utf-8"):
            fails.append("stale_creds draft missing status: draft frontmatter")


def test_promote(fails: list[str]) -> None:
    if not GOLD.is_file():
        fails.append(f"missing gold fixture: {GOLD}")
        return
    with tempfile.TemporaryDirectory() as tmp:
        drafts = Path(tmp) / "playbooks" / "_drafts"
        drafts.mkdir(parents=True)
        gold_copy = drafts / "gold-stale_creds.md"
        gold_copy.write_text(GOLD.read_text(encoding="utf-8"), encoding="utf-8")

        r = _run([sys.executable, str(PROMOTE), str(gold_copy)])
        if r.returncode != 0:
            fails.append(f"promote gold: expected 0, got {r.returncode}: {r.stderr}")
        active = Path(tmp) / "playbooks" / "gold-stale_creds.md"
        if not active.is_file():
            fails.append(f"promote gold: missing active {active}")
        elif "status: active" not in active.read_text(encoding="utf-8"):
            fails.append("promote gold: active file missing status: active")
        if gold_copy.exists():
            fails.append("promote gold: draft should be moved/removed")
        if "checklist" not in (r.stdout or ""):
            fails.append("promote gold: expected checklist on stdout")

        # Incomplete draft must fail
        bad = drafts / "incomplete.md"
        bad.write_text(
            "---\nstatus: draft\nslot: env_setup\nkind: playbook\n"
            "source_episodes: [x]\ncluster: default\nincomplete: true\n---\n\n"
            "# bad\n\n## Steps\n\n1. a\n2. b\n\n## Avoid\n\n- x\n",
            encoding="utf-8",
        )
        r = _run([sys.executable, str(PROMOTE), str(bad)])
        if r.returncode == 0:
            fails.append("promote incomplete: expected nonzero")


def test_playbook_loader_skips_drafts(fails: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "playbooks"
        (root / "_drafts").mkdir(parents=True)
        (root / "active.md").write_text("# active\n", encoding="utf-8")
        (root / "_drafts" / "hidden.md").write_text("# draft\n", encoding="utf-8")
        (root / "_archive").mkdir()
        (root / "_archive" / "old.md").write_text("# old\n", encoding="utf-8")
        found = RT.iter_playbooks(root)
        names = {p.name for p in found}
        if "active.md" not in names:
            fails.append(f"iter_playbooks missed active.md: {names}")
        if "hidden.md" in names:
            fails.append("iter_playbooks must skip _drafts")
        if "old.md" in names:
            fails.append("iter_playbooks must skip _archive")


def main() -> int:
    fails = []
    for query, domain in PREF_CASES:
        got = [p["domain"] for p in RT.preferences(query)]
        if domain and domain not in got:
            fails.append(f"prefs {query!r}: expected {domain}, got {got}")
        if not domain and got:
            fails.append(f"prefs {query!r}: expected none, got {got}")
    prefs = RT.preferences("打开浏览器")
    if not prefs or not prefs[0]["prefs"]:
        fails.append("preferences.md parsed but prefs list empty — 格式坏了")
    for query in ("打开浏览器验证下页面", "跑一下核心回归", "看下报错日志"):
        got = [p["domain"] for p in RT.preferences(query)]
        if len(got) > 1:
            fails.append(f"prefs {query!r}: 触发词重叠，注入了 {got}")

    for query, expected in CASES:
        got = next((n for p, n in RT.ALIASES if p.search(query)), None)
        if got != expected:
            fails.append(f"alias {query!r}: expected {expected}, got {got}")

    for ep in JUNK:
        if not is_junk(ep):
            fails.append(f"junk not detected: {ep['task']!r}")
    for ep in NOT_JUNK:
        if is_junk(ep):
            fails.append(f"false junk: {ep['task']!r}")
    if is_thin({"task": "x", "preferred_path": ["跑 python3 -m pytest"], "outcome": {"ok": True}}):
        fails.append("concrete step should not count as thin")

    bad_lesson = "token_in_chat 密钥进对话 只收 PAT，askpass 用完即弃，轨迹写 <PAT>"
    if not discard_secret_without_store(bad_lesson):
        fails.append("discard_secret_without_store should flag 用完即弃")
    fixed = normalize_lesson(bad_lesson)
    if "【纠偏】" not in fixed or ".llm-trace-reuse/secrets" not in fixed:
        fails.append(f"normalize_lesson should append store-reuse: {fixed!r}")
    ok_lesson = "写入 .llm-trace-reuse/secrets 覆盖复用；失败再问 token"
    if discard_secret_without_store(ok_lesson):
        fails.append("local-store advice must not be treated as discard-only")
    if path_missing_auth_lifecycle(["GIT_ASKPASS one-shot", "git push origin"]):
        pass
    else:
        fails.append("ASKPASS+push without save should be auth lifecycle gap")
    if path_missing_auth_lifecycle(
        ["失败问 token", "save .llm-trace-reuse/secrets", "push 读本地"]
    ):
        fails.append("full auth lifecycle path should not be a gap")

    # Open-source phrasing must not steal the git-push alias.
    oss = "可以的，需要在个人 github 上开源，新起个项目，业务代码不能推送"
    if next((n for p, n in RT.ALIASES if p.search(oss)), None) == "git-push":
        fails.append("open-source request must not alias to git-push")

    # --- distill SOP extras (beyond the original 31) ---
    test_append_mode_gate(fails)
    test_distill_drafts(fails)
    test_promote(fails)
    test_playbook_loader_skips_drafts(fails)

    for f in fails:
        print("FAIL " + f, file=sys.stderr)
    extra = 6
    total = len(CASES) + len(PREF_CASES) + len(JUNK) + len(NOT_JUNK) + extra
    print(f"{total} base checks + distill-sop extras, {len(fails)} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
