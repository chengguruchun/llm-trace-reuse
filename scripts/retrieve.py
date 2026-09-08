#!/usr/bin/env python3
"""Retrieve similar past episodes so a new request can reuse preferred_path."""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import traces_dir  # noqa: E402
from quality import lessons  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff]")
WORD = re.compile(r"[a-z0-9_\-]{2,}")


def tokens(text: str) -> set[str]:
    s = (text or "").lower()
    words = set(WORD.findall(s))
    chars = CJK.findall(s)
    grams = set(chars)
    grams.update(chars[i] + chars[i + 1] for i in range(len(chars) - 1))
    return words | grams


# Quarantine / backup copies must not come back through rglob.
# Convention: any directory whose name starts with `_` is isolated.
EXCLUDE_DIRS = {"_pruned", "_migrated-legacy"}


def _excluded(rel_parts: tuple[str, ...]) -> bool:
    return any(p in EXCLUDE_DIRS or p.startswith("_") for p in rel_parts[:-1])


def load_episodes(root: Path) -> list[dict]:
    out = []
    if not root.exists():
        return out
    for path in sorted(root.rglob("*.jsonl")):
        if path.name == "bad-cases.jsonl":
            continue
        if _excluded(path.relative_to(root).parts):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def blob(ep: dict) -> str:
    parts = [ep.get("task") or ""]
    parts.extend(ep.get("constraints") or [])
    parts.extend(ep.get("preferred_path") or [])
    for d in ep.get("decisions") or []:
        if isinstance(d, dict):
            parts.append(str(d.get("point") or ""))
            parts.append(str(d.get("choice") or ""))
    parts.extend(lessons(ep))
    return " ".join(parts)


# Thresholds live here only. Recalibrated on task-as-query, leave-one-out:
# reuse must be precise (skipping the plan is expensive) → 0.30;
# avoid can be looser (missing a lesson costs more than reading an extra one) → 0.24.
REUSE_MIN_SCORE = 0.30
AVOID_MIN_SCORE = 0.24
SWEEP_THRESHOLDS = (0.20, 0.24, 0.30, 0.36, 0.45, 0.60)

# Coverage saturates on tiny queries ("run tests" has ~5 distinctive tokens).
# Gate reuse at 8 tokens; avoid still fires.
MIN_QUERY_TOKENS = 8


def jaccard(a: set[str], b: set[str]) -> float:
    """Kept for ablation; routing uses similarity()."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def idf_map(eps: list[dict]) -> dict[str, float]:
    n = len(eps) or 1
    df: Counter[str] = Counter()
    for ep in eps:
        for t in tokens(blob(ep)):
            df[t] += 1
    return {t: math.log((n + 1) / (1 + d)) for t, d in df.items()}


def similarity(q: set[str], doc: set[str], idf: dict[str, float]) -> float:
    """IDF-weighted query coverage. Independent of document length.

    Jaccard punishes well-written episodes: a longer blob has a larger union
    and a lower score. Coverage normalizes by the query only; IDF zeroes out
    tokens that appear in every episode.
    """
    if not q or not doc:
        return 0.0
    weights = {t: idf.get(t, 0.0) for t in q}
    denom = sum(w for w in weights.values() if w > 0)
    if denom <= 0:
        return 0.0
    num = sum(w for t, w in weights.items() if w > 0 and t in doc)
    return num / denom


def trust_map(eps: list[dict]) -> dict[str, float]:
    """How well did reusing each episode actually turn out?

    Derived from later episodes' `retrieved[].used` plus their own outcome.
    Laplace-smoothed to 0.5 (= neutral). Applied as `score × (0.5 + trust)`.
    """
    wins: Counter[str] = Counter()
    losses: Counter[str] = Counter()
    for ep in eps:
        outcome = ep.get("outcome")
        ok = outcome.get("ok") is not False if isinstance(outcome, dict) else True
        for r in ep.get("retrieved") or []:
            if isinstance(r, dict) and r.get("used") is True and r.get("id"):
                (wins if ok else losses)[str(r["id"])] += 1
    ids = set(wins) | set(losses)
    return {i: (1 + wins[i]) / (2 + wins[i] + losses[i]) for i in ids}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: retrieve.py <query> [root]", file=sys.stderr)
        return 2
    query = sys.argv[1]
    root = Path(sys.argv[2] if len(sys.argv) > 2 else traces_dir())
    q = tokens(query)
    eps = load_episodes(root)
    trust = trust_map(eps)
    idf = idf_map(eps)
    ranked = []
    for ep in eps:
        raw = similarity(q, tokens(blob(ep)), idf)
        if raw <= 0:
            continue
        t = trust.get(str(ep.get("id")), 0.5)
        ranked.append((raw * (0.5 + t), raw, t, ep))
    ranked.sort(key=lambda x: x[0], reverse=True)

    reuse, avoid = [], []
    for score, raw, t, ep in ranked[:8]:
        item = {
            "id": ep.get("id"),
            "score": round(score, 4),
            "similarity": round(raw, 4),
            "trust": round(t, 3),
            "task": ep.get("task"),
            "preferred_path": ep.get("preferred_path") or [],
            "decisions": ep.get("decisions") or [],
            "bad_case": bool(ep.get("bad_case")),
            "lessons": lessons(ep)[:3],
        }
        if ep.get("outcome", {}).get("ok") is False or ep.get("bad_case"):
            avoid.append(item)
        else:
            reuse.append(item)

    result = {
        "query": query,
        "query_tokens": sum(1 for t in q if idf.get(t, 0.0) > 0),
        "min_query_tokens": MIN_QUERY_TOKENS,
        "reuse": reuse[:3],
        "avoid": avoid[:3],
        "hint": f"score>={REUSE_MIN_SCORE} 且 reuse 非空 → 先走 preferred_path / decisions，不要重探",
        "scoring": (
            "similarity = IDF-weighted query coverage (length-independent); "
            "score = similarity × (0.5 + trust); "
            "trust from later retrieved.used + outcome, 0.5 = unproven"
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
