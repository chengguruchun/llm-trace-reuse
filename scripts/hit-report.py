#!/usr/bin/env python3
"""Analyse WHY routing hits or misses, so thresholds/aliases are tuned on evidence.

  hit-report.py            # summary
  hit-report.py --verbose  # + marginal hits and dead-stock ids

All reuse numbers are leave-one-out: an episode never matches itself.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retrieve as R  # noqa: E402
import route as RT  # noqa: E402
from paths import traces_dir  # noqa: E402
from quality import is_junk, is_thin  # noqa: E402

THRESHOLDS = list(R.SWEEP_THRESHOLDS)
MARGINAL_BAND = (R.REUSE_MIN_SCORE, round(R.REUSE_MIN_SCORE + 0.04, 2))


def alias_for(text: str) -> str | None:
    for pat, name in RT.ALIASES:
        if pat.search(text or ""):
            return name
    return None


def main() -> int:
    verbose = "--verbose" in sys.argv
    root = Path(next((a for a in sys.argv[1:] if not a.startswith("--")), traces_dir()))
    eps = [e for e in R.load_episodes(root) if isinstance(e, dict) and e.get("id")]
    if not eps:
        print(json.dumps({"episodes": 0}, ensure_ascii=False, indent=2))
        return 0

    toks = {e["id"]: R.tokens(R.blob(e)) for e in eps}
    qtoks = {e["id"]: R.tokens(e.get("task") or "") for e in eps}
    idf = R.idf_map(eps)
    by_id = {e["id"]: e for e in eps}

    best: dict[str, tuple[float, str | None]] = {}
    top1_count: Counter[str] = Counter()
    for e in eps:
        eid = e["id"]
        score, who = 0.0, None
        for o in eps:
            oid = o["id"]
            if oid == eid:
                continue
            s = R.similarity(qtoks[eid], toks[oid], idf)
            if s > score:
                score, who = s, oid
        best[eid] = (score, who)
        if who and score >= R.REUSE_MIN_SCORE:
            top1_count[who] += 1

    alias_fired: Counter[str] = Counter()
    alias_tasks: dict[str, list[str]] = {}
    for e in eps:
        name = alias_for(e.get("task") or "")
        if name:
            alias_fired[name] += 1
            alias_tasks.setdefault(name, []).append(e["id"])
    declared = [name for _, name in RT.ALIASES]
    dead_alias = [n for n in declared if not alias_fired.get(n)]

    no_alias = [e for e in eps if not alias_for(e.get("task") or "")]
    sweep = []
    for t in THRESHOLDS:
        n = sum(1 for e in no_alias if best[e["id"]][0] >= t)
        sweep.append({
            "threshold": t,
            "would_reuse": n,
            "pct_of_non_alias": round(n / len(no_alias), 3) if no_alias else 0.0,
        })

    dead_stock = [e["id"] for e in eps if top1_count.get(e["id"], 0) == 0]

    marginal = []
    for e in no_alias:
        s, who = best[e["id"]]
        if MARGINAL_BAND[0] <= s < MARGINAL_BAND[1] and who:
            marginal.append({
                "query_episode": e["id"],
                "matched": who,
                "score": round(s, 4),
                "matched_path": (by_id[who].get("preferred_path") or [])[:2],
            })
    marginal.sort(key=lambda x: x["score"])

    with_lessons = [e for e in eps if R.lessons(e)]
    failures = [e for e in eps if e.get("bad_case") or (e.get("outcome") or {}).get("ok") is False]
    avoid_reachable = sum(
        1 for e in eps
        if any(
            R.similarity(qtoks[e["id"]], toks[o["id"]], idf) >= R.AVOID_MIN_SCORE
            for o in with_lessons if o["id"] != e["id"]
        )
    )

    out = {
        "episodes": len(eps),
        "alias": {
            "fired_on_history": dict(alias_fired.most_common()),
            "dead_aliases": dead_alias,
            "covered_pct": round(sum(alias_fired.values()) / len(eps), 3),
            "hint": "dead alias = 规则写了但没人这么说话；考虑删或换触发词",
        },
        "threshold_sweep": sweep,
        "current_threshold": R.REUSE_MIN_SCORE,
        "avoid_threshold": R.AVOID_MIN_SCORE,
        "non_alias_episodes": len(no_alias),
        "dead_stock": {
            "count": len(dead_stock),
            "pct": round(len(dead_stock) / len(eps), 3),
            "hint": "从没被任何查询选中过；不等于没用，别据此删",
        },
        "marginal_hits": {
            "count": len(marginal),
            "band": list(MARGINAL_BAND),
            "hint": "刚过复用阈值那一档，最可能误触",
        },
        "avoid_supply": {
            "episodes_with_lessons": len(with_lessons),
            "failure_episodes": len(failures),
            "episodes_reachable_by_some_avoid": avoid_reachable,
            "pct": round(avoid_reachable / len(eps), 3),
            "hint": "占比太低说明失败知识写得太少或措辞对不上",
        },
        "corpus_quality": {
            "junk": sum(1 for e in eps if is_junk(e)),
            "thin": sum(1 for e in eps if is_thin(e)),
            "hint": "junk>0 跑 prune-junk.py；thin 高说明 append 时没记 decisions/critique",
        },
    }
    if verbose:
        out["dead_stock"]["ids"] = dead_stock
        out["marginal_hits"]["items"] = marginal[:15]
        out["alias"]["examples"] = {k: v[:3] for k, v in alias_tasks.items()}

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
