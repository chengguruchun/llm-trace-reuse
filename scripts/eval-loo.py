#!/usr/bin/env python3
"""Leave-one-out reuse potential (never score an episode against itself)."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import traces_dir  # noqa: E402
from retrieve import REUSE_MIN_SCORE, blob, idf_map, similarity, tokens  # noqa: E402
from retrieve import load_episodes as _load  # noqa: E402

STRONG_SCORE = round(REUSE_MIN_SCORE * 1.6, 2)


def load_episodes(root: Path) -> list[dict]:
    return [e for e in _load(root) if isinstance(e, dict) and e.get("id")]


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else traces_dir())
    eps = load_episodes(root)
    if not eps:
        print(json.dumps({"episodes": 0}, ensure_ascii=False, indent=2))
        return 0

    buckets = Counter()
    with_retrieved = used_true = 0
    idf = idf_map(eps)
    docs = {e["id"]: tokens(blob(e)) for e in eps}
    for e in eps:
        retrieved = e.get("retrieved")
        if isinstance(retrieved, list):
            with_retrieved += 1
            if any(isinstance(r, dict) and r.get("used") is True for r in retrieved):
                used_true += 1

        q = tokens(e.get("task") or "")
        best = 0.0
        for o in eps:
            if o.get("id") == e.get("id"):
                continue
            best = max(best, similarity(q, docs[o["id"]], idf))
        if best >= STRONG_SCORE:
            buckets["strong"] += 1
        elif best >= REUSE_MIN_SCORE:
            buckets["usable"] += 1
        else:
            buckets["miss"] += 1

    playbooks = list((root / "playbooks").glob("*.md")) if (root / "playbooks").exists() else []
    n = len(eps)
    print(json.dumps({
        "episodes_with_id": n,
        "query": "task（贴合路由时的真实输入，不用整条 blob）",
        "thresholds": {"reuse": REUSE_MIN_SCORE, "strong": STRONG_SCORE},
        f"loo_ge_{STRONG_SCORE}": buckets["strong"],
        f"loo_{REUSE_MIN_SCORE}_{STRONG_SCORE}": buckets["usable"],
        f"loo_lt_{REUSE_MIN_SCORE}": buckets["miss"],
        "loo_reuse_pct": round((buckets["strong"] + buckets["usable"]) / n, 3),
        "episodes_with_retrieved": with_retrieved,
        "retrieved_used_true": used_true,
        "retrieved_fill_pct": round(with_retrieved / n, 3),
        "used_among_all_pct": round(used_true / n, 3),
        "playbooks": sorted(p.name for p in playbooks),
        "note": "KPI = retrieved fill/used + playbook count; do NOT use self-inclusive retrieve hit rate",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
