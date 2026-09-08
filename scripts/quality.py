#!/usr/bin/env python3
"""One definition of "is this episode worth retrieving", shared by
append-episode (gate), hit-report (metric) and prune-junk (cleanup).

junk = not a task at all (ack / notification / one-liner) AND carries no signal.
thin = a real task, but nothing reusable was recorded.
"""
from __future__ import annotations

import re

# Concrete = names a command, path, file or symbol someone could act on.
CONCRETE = re.compile(
    r"[/\\]\w|\.\w{2,4}\b|`|--|\b(dotnet|docker|git|bash|python3?|curl|sql|http)\b"
    r"|[A-Za-z_]+\.[A-Za-z_]+"
)

# Phrasings that mark a record as bookkeeping rather than work.
NON_TASK = re.compile(
    r"(用户确认.*(ok|通过|结果)|用户说\s*ok|^\s*ok[\s，。!]*$|系统通知"
    r"|[（(]短问[)）]|短问$|^确认$|^收到|^好的"
    r"|user\s+confirmed|ack(?:ed)?$|lgtm\b)",
    re.I,
)


# critique 里装建议正文的字段。历史上写法不统一（note / cost+better / fix 都有），
# 只读 mode+note 会把一半以上的建议丢掉，索引里只剩光秃秃的 slug，
# 于是 avoid 通道对中文 query 永远匹配不上。
CRITIQUE_TEXT_FIELDS = ("mode", "note", "cost", "better", "fix")

# 踩过的蒸馏偏差：把 secret_hygiene 收成「用完即弃」，挡住本机复用。
# 历史 jsonl 不改；检索/avoid 出口纠偏，append 时告警。
_DISCARD_ONLY = re.compile(r"用完即弃|askpass\s*用完|用完即删|discard\s+after\s+use", re.I)
_LOCAL_STORE = re.compile(
    r"\.pathbook/secrets|\.local/secrets|本机.*(存|覆盖)|覆盖.*写入|gitignored.*store",
    re.I,
)
SECRET_HYGIENE_BETTER = (
    "令牌不进 URL/对话明文；写入 .pathbook/secrets（覆盖）下次复用；"
    "失败再问用户要新 token"
)

# preferred_path 写了推/ASKPASS 却没有失败问令牌或本机存 → 闭环不完整。
_AUTH_MARK = re.compile(r"\b(push|askpass|pat|token)\b|推送?|令牌|远端", re.I)
_LIFECYCLE_MARK = re.compile(
    r"save|\.pathbook/secrets|\.local/secrets|失败|问.*token|"
    r"要.*(?:token|pat|令牌)|覆盖|复用|ask.*user",
    re.I,
)


def discard_secret_without_store(text: str) -> bool:
    s = (text or "").strip()
    return bool(s) and bool(_DISCARD_ONLY.search(s)) and not _LOCAL_STORE.search(s)


def normalize_lesson(text: str) -> str:
    """Retrieval-side rewrite so old 「用完即弃」 lessons stop teaching discard-only."""
    s = (text or "").strip()
    if not s:
        return s
    if discard_secret_without_store(s):
        return f"{s} 【纠偏】secret_hygiene≠用完即弃：{SECRET_HYGIENE_BETTER}"
    return s


def path_missing_auth_lifecycle(steps: list | tuple) -> bool:
    blob = " ".join(str(x) for x in (steps or []))
    if not _AUTH_MARK.search(blob):
        return False
    return not _LIFECYCLE_MARK.search(blob)


def critique_items(ep: dict) -> list:
    """critique 允许写成 dict / list / str，统一成可迭代的条目。

    不做这层规整时，dict 会被 `for c in critique` 迭代成**键名**，
    再被 isinstance(c, str) 当成教训收进索引（实测抽出 ['mode', 'fix']）。
    """
    c = ep.get("critique")
    if isinstance(c, dict):
        return [c]
    if isinstance(c, list):
        return c
    if isinstance(c, str) and c.strip():
        return [c]
    return []


def lessons(ep: dict) -> list[str]:
    out = []
    for c in critique_items(ep):
        if isinstance(c, dict):
            parts = [
                str(c.get(k)).strip()
                for k in CRITIQUE_TEXT_FIELDS
                if str(c.get(k) or "").strip()
            ]
            if parts:
                out.append(normalize_lesson(" ".join(parts)))
        elif isinstance(c, str):
            out.append(normalize_lesson(c))
    # Legacy reward_hints are scoring dicts ({"signal":…,"delta":1}), not advice.
    # Stringifying them poisons the index and fakes avoid supply.
    out.extend(
        normalize_lesson(h)
        for h in (ep.get("reward_hints") or [])
        if isinstance(h, str) and h.strip()
    )
    return [s for s in out if s.strip()]


def value_signals(ep: dict) -> dict:
    outcome = ep.get("outcome")
    steps = [str(x) for x in (ep.get("preferred_path") or [])]
    return {
        "decisions": sum(
            1
            for d in (ep.get("decisions") or [])
            if isinstance(d, dict) and len(d.get("options") or []) >= 2
        ),
        "lessons": len(lessons(ep)),
        "tests": bool(outcome.get("tests")) if isinstance(outcome, dict) else bool(outcome),
        "concrete_steps": sum(1 for s in steps if CONCRETE.search(s)),
        "steps": len(steps),
    }


def is_thin(ep: dict) -> bool:
    s = value_signals(ep)
    return not (s["decisions"] or s["lessons"] or s["tests"] or s["concrete_steps"])


def is_junk(ep: dict) -> bool:
    return is_thin(ep) and bool(NON_TASK.search(str(ep.get("task") or "")))


def why_thin(ep: dict) -> str:
    return (
        "没有 options≥2 的 decisions、没有 critique/reward_hints、没有 outcome.tests，"
        "preferred_path 也没有可执行的命令/路径 —— 检索到它也用不上"
    )
