#!/usr/bin/env python3
"""Decide playbook vs reuse vs LLM before spending model tokens."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
RETRIEVE = SCRIPTS / "retrieve.py"

sys.path.insert(0, str(SCRIPTS))
from paths import traces_dir  # noqa: E402
from retrieve import (  # noqa: E402
    AVOID_MIN_SCORE,
    MIN_QUERY_TOKENS,
    REUSE_MIN_SCORE,
)

# Built-in aliases: high-confidence intents that should not open a planning chat.
# Keep these generic. Project-specific SOPs belong in playbooks + extra aliases
# you add locally — do not put product names in this file.
SCRIPT_ENTRY = {
    "distill": SCRIPTS / "distill.py",
    "retrieve": SCRIPTS / "retrieve.py",
    "eval-loo": SCRIPTS / "eval-loo.py",
    "git-push": None,
    "run-tests": None,
}

# Bare "push" / "推送" is too wide: "can we open-source and push" is not git-push.
ALIASES = [
    (
        re.compile(
            r"(推到远端|推远端|推上去|推一?下|把.+推到|^推$"
            r"|(?:^|请|执行|跑)\s*git\s*push|^git\s*push\b)"
        ),
        "git-push",
    ),
    (
        re.compile(
            r"((跑|执行)一?下?(核心)?(回归)?(测试|单测)|\brun\s+(the\s+)?tests?\b)"
        ),
        "run-tests",
    ),
    (re.compile(r"(蒸馏|distill|失败模式统计)"), "distill"),
    (
        re.compile(r"((跑|查|走|来|执行)一?下?\s*(检索|retrieve)|^retrieve\b|找相似|相似路径|类似的?历史)"),
        "retrieve",
    ),
    (re.compile(r"(leave-?one-?out|eval-?loo|复用潜力|效率评估)"), "eval-loo"),
]


def retrieve(query: str) -> dict:
    home = traces_dir()
    proc = subprocess.run(
        [sys.executable, str(RETRIEVE), query, str(home)],
        cwd=str(home.parent if home.exists() else Path.cwd()),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def preferences(query: str) -> list[dict]:
    """Tool/habit choices, matched by keyword and emitted on every route.

    Separate from playbooks: a playbook only fires when an alias hits, but
    "which browser / which test command" must hold even on novel tasks.
    """
    pref_path = traces_dir() / "preferences.md"
    if not pref_path.exists():
        return []
    q = query.lower()
    out, domain, triggers, items = [], None, [], []

    def flush():
        if domain and items and any(t and t.lower() in q for t in triggers):
            out.append({"domain": domain, "prefs": list(items)})

    for line in pref_path.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if line.startswith("## "):
            flush()
            domain, triggers, items = line[3:].strip(), [], []
        elif line.startswith("触发：") and domain:
            triggers = line[3:].split()
        elif line.startswith("- ") and domain:
            items.append(line[2:].strip())
    flush()
    return out


def compact_avoid(hit: dict) -> list[dict]:
    out = []
    for kind, key in (("failure", "avoid"), ("lesson", "reuse")):
        for item in hit.get(key) or []:
            lessons = item.get("lessons") or []
            if not lessons or (item.get("score") or 0) < AVOID_MIN_SCORE:
                continue
            out.append({
                "id": item.get("id"),
                "score": item.get("score"),
                "from": kind,
                "task": item.get("task"),
                "lessons": lessons,
            })
    out.sort(key=lambda x: (x["from"] != "failure", -(x["score"] or 0)))
    return out[:3]


def emit(payload: dict, avoid: list[dict], prefs: list[dict]) -> int:
    if prefs:
        payload["preferences"] = prefs
        payload["preferences_hint"] = "用户既定选型，直接照做，不要重新挑工具"
    if avoid:
        payload["avoid"] = avoid
        payload["avoid_hint"] = "已踩过的坑，别重探；先排除这些路径"
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: route.py <query>", file=sys.stderr)
        return 2
    query = sys.argv[1]
    hit = retrieve(query)
    avoid = compact_avoid(hit)
    prefs = preferences(query)
    playbooks = traces_dir() / "playbooks"

    for pat, name in ALIASES:
        if pat.search(query):
            pb = playbooks / f"{name}.md"
            script = SCRIPT_ENTRY.get(name)
            script_path = str(script) if script and Path(script).exists() else None
            return emit({
                "route": "playbook" if pb.exists() else "script",
                "name": name,
                "playbook": str(pb) if pb.exists() else None,
                "script": script_path,
                "llm": "skip-plan; only call model if a playbook step fails",
                "reason": f"alias:{name}",
            }, avoid, prefs)

    reuse = (hit.get("reuse") or [None])[0]
    score = (reuse or {}).get("score") or 0
    long_enough = hit.get("query_tokens", 0) >= MIN_QUERY_TOKENS
    if reuse and score >= REUSE_MIN_SCORE and long_enough:
        return emit({
            "route": "reuse",
            "name": reuse.get("id"),
            "preferred_path": reuse.get("preferred_path") or [],
            "llm": "no planning; execute preferred_path; model only on failure",
            "reason": f"retrieve:{score}",
        }, avoid, prefs)

    return emit({
        "route": "llm",
        "inject": [],
        "llm": "needed — novel task; inject only short path, not jsonl",
        "reason": (
            f"query 太短（{hit.get('query_tokens', 0)} < {MIN_QUERY_TOKENS} 个有区分度的词），"
            "覆盖率会饱和，不敢直接复用别人的 preferred_path"
            if reuse and score >= REUSE_MIN_SCORE and not long_enough
            else "no playbook/reuse hit"
        ),
    }, avoid, prefs)


if __name__ == "__main__":
    raise SystemExit(main())
