#!/usr/bin/env python3
"""Quarantine non-task rows that only dilute retrieval.

  prune-junk.py            # dry run
  prune-junk.py --apply    # move them to <traces>/_pruned/

Quarantined, never deleted — restore by moving lines back.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import traces_dir  # noqa: E402
from quality import is_junk, value_signals  # noqa: E402

SKIP_DIRS = {"_pruned", "_migrated-legacy"}


def sources(traces: Path) -> list[Path]:
    if not traces.exists():
        return []
    return [
        p
        for p in sorted(traces.rglob("*.jsonl"))
        if p.name != "bad-cases.jsonl" and not SKIP_DIRS & set(p.relative_to(traces).parts)
    ]


def main() -> int:
    apply = "--apply" in sys.argv
    traces = traces_dir()
    pruned_dir = traces / "_pruned"
    moved: list[dict] = []
    edits: dict[Path, tuple[list[str], list[str]]] = {}

    for path in sources(traces):
        keep: list[str] = []
        drop: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ep = json.loads(line)
            except json.JSONDecodeError:
                keep.append(line)
                continue
            if isinstance(ep, dict) and is_junk(ep):
                drop.append(line)
                moved.append({"file": path.name, "id": ep.get("id"), "task": ep.get("task"),
                              "signals": value_signals(ep)})
            else:
                keep.append(line)
        if drop:
            edits[path] = (keep, drop)

    if apply and moved:
        pruned_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        with (pruned_dir / f"{stamp}.jsonl").open("a", encoding="utf-8") as f:
            for _, drop in edits.values():
                f.write("".join(line + "\n" for line in drop))
        for path, (keep, _) in edits.items():
            path.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")

    print(json.dumps({
        "mode": "apply" if apply else "dry-run",
        "files_touched": [p.name for p in edits],
        "pruned": len(moved),
        "items": moved,
        "hint": "" if apply else "加 --apply 才真的移动",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
