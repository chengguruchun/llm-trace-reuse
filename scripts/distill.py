#!/usr/bin/env python3
"""Count repeated critique slots — candidates to distill into rules/skills.

按 modes.py 的**槽位**聚合，不是按 mode 原文。原文粒度太细时精确计数几乎
永远不触发 count>=2，蒸馏因此空转。

另报 auth_path_gaps：preferred_path 写了推/令牌却缺「失败问 / 本机存」生命周期。
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modes import SLOT_DESC, UNCLASSIFIED, slot_of  # noqa: E402
from paths import traces_dir  # noqa: E402
from quality import critique_items, path_missing_auth_lifecycle  # noqa: E402
from retrieve import load_episodes  # noqa: E402

THRESHOLD = 2
LIFECYCLE_SLOTS = frozenset({"secret_hygiene", "stale_creds"})


def action_for(slot: str, count: int) -> str:
    if count < THRESHOLD:
        return "再攒一次"
    if slot in LIFECYCLE_SLOTS:
        return (
            "写/改 playbook+脚本：失败问 token→.pathbook/secrets 覆盖→下次复用；"
            "secret_hygiene≠用完即弃（禁的是 URL/对话明文）"
        )
    return "count>=2 → 写更短 playbook/脚本，勿加长 alwaysApply"


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else traces_dir())
    slots: Counter[str] = Counter()
    raw_modes: dict[str, Counter[str]] = defaultdict(Counter)
    episodes_of: dict[str, list[str]] = defaultdict(list)
    advice: dict[str, list[str]] = defaultdict(list)
    auth_gaps: list[str] = []

    eps = [e for e in load_episodes(root) if isinstance(e, dict)]
    for ep in eps:
        eid = ep.get("id") or ""
        if path_missing_auth_lifecycle(ep.get("preferred_path") or []):
            if eid:
                auth_gaps.append(eid)
        for c in critique_items(ep):
            if not isinstance(c, dict):
                continue
            mode = (c.get("mode") or "").strip()
            if not mode:
                continue
            slot = slot_of(mode)
            slots[slot] += 1
            raw_modes[slot][mode[:60]] += 1
            if eid and eid not in episodes_of[slot]:
                episodes_of[slot].append(eid)
            for key in ("better", "fix", "note"):
                text = str(c.get(key) or "").strip()
                if text:
                    advice[slot].append(text[:120])
                    break

    ripe = [s for s, n in slots.items() if n >= THRESHOLD and s != UNCLASSIFIED]
    print(json.dumps({
        "episodes": len(eps),
        "slots_total": len(slots),
        "ripe_for_distill": len(ripe),
        "threshold": THRESHOLD,
        "auth_path_gaps": {
            "count": len(auth_gaps),
            "hint": "preferred_path 含推/令牌但缺失败问/本机存 — 蒸馏时补生命周期",
            "examples": auth_gaps[:8],
        },
        "distill": [
            {
                "slot": slot,
                "means": SLOT_DESC.get(slot, "未归类，请补 modes.py 的关键词"),
                "count": count,
                "raw_modes": raw_modes[slot].most_common(6),
                "episodes": episodes_of[slot][:6],
                "advice_seen": advice[slot][:3],
                "action": action_for(slot, count),
            }
            for slot, count in slots.most_common(20)
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
