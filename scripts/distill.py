#!/usr/bin/env python3
"""Count repeated critique slots and write playbook drafts under playbooks/_drafts/.

Per-episode-per-slot counting (each id ≤1). Lifecycle slots secret_hygiene /
stale_creds ripen at 1; others at 2. unclassified is never ripe.

Only kind=playbook writes markdown drafts. Route ignores `_drafts/` (and any
`_*` directory). Promote with promote-playbook.py.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modes import SLOT_DESC, UNCLASSIFIED, slot_of  # noqa: E402
from paths import traces_dir  # noqa: E402
from quality import (  # noqa: E402
    CONCRETE,
    critique_items,
    path_missing_auth_lifecycle,
)
from retrieve import jaccard, load_episodes, tokens  # noqa: E402

THRESHOLD = 2
LIFECYCLE_SLOTS = frozenset({"secret_hygiene", "stale_creds"})
CLUSTER_JACCARD = 0.30
SHORT_LESSON_CHARS = 80


def threshold_for(slot: str) -> int:
    return 1 if slot in LIFECYCLE_SLOTS else THRESHOLD


def action_for(slot: str, count: int, kind: str) -> str:
    need = threshold_for(slot)
    if count < need:
        return "再攒一次"
    if kind == "playbook":
        if slot in LIFECYCLE_SLOTS:
            return (
                "已写 _drafts：失败问 token→.llm-trace-reuse/secrets 覆盖→下次复用；"
                "promote-playbook 后再加 alias"
            )
        return "已写 _drafts → promote-playbook；勿加长 alwaysApply"
    if kind == "preference":
        return "建议追加 preferences.md 一条短习惯（~20 tokens），不写 SOP"
    return "avoid 卡：短笔记即可，不建 alias"


def episode_slot_text(ep: dict, slot: str) -> str:
    parts = [str(x) for x in (ep.get("preferred_path") or [])]
    for c in critique_items(ep):
        if not isinstance(c, dict):
            continue
        if slot_of(str(c.get("mode") or "")) != slot:
            continue
        for key in ("better", "fix", "note"):
            text = str(c.get(key) or "").strip()
            if text:
                parts.append(text)
                break
    return " ".join(parts)


def cluster_episodes(eps: list[dict], slot: str) -> list[list[dict]]:
    """Greedy connected components by Jaccard on preferred_path + better tokens."""
    if not eps:
        return []
    tok = [tokens(episode_slot_text(ep, slot)) for ep in eps]
    n = len(eps)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if jaccard(tok[i], tok[j]) >= CLUSTER_JACCARD:
                union(i, j)

    groups: dict[int, list[dict]] = defaultdict(list)
    for i, ep in enumerate(eps):
        groups[find(i)].append(ep)
    # Stable order: by first episode id
    clusters = sorted(groups.values(), key=lambda g: str(g[0].get("id") or ""))
    return clusters


def merged_concrete_count(eps: list[dict]) -> int:
    seen: set[str] = set()
    n = 0
    for ep in eps:
        for step in ep.get("preferred_path") or []:
            s = str(step).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            if CONCRETE.search(s):
                n += 1
    return n


def short_lessons(eps: list[dict], slot: str) -> bool:
    texts: list[str] = []
    for ep in eps:
        for c in critique_items(ep):
            if not isinstance(c, dict):
                continue
            if slot_of(str(c.get("mode") or "")) != slot:
                continue
            for key in ("better", "fix", "note", "cost"):
                t = str(c.get(key) or "").strip()
                if t:
                    texts.append(t)
    if not texts:
        return False
    return all(len(t) <= SHORT_LESSON_CHARS for t in texts)


def kind_for(slot: str, eps: list[dict]) -> str:
    if slot in LIFECYCLE_SLOTS:
        return "playbook"
    if merged_concrete_count(eps) >= 2:
        return "playbook"
    if short_lessons(eps, slot):
        return "preference"
    return "avoid"


def vote_steps(eps: list[dict], slot: str) -> list[str]:
    """Vote preferred_path by position; graft better/fix failure hints."""
    paths = [
        [str(x).strip() for x in (ep.get("preferred_path") or []) if str(x).strip()]
        for ep in eps
    ]
    paths = [p for p in paths if p]
    steps: list[str] = []
    if paths:
        # Prefer the path with the most concrete steps as the skeleton.
        base = max(paths, key=lambda p: (sum(1 for s in p if CONCRETE.search(s)), len(p)))
        steps = list(base)
        # Position-wise: if a majority prefers another phrasing at i, swap.
        max_len = max(len(p) for p in paths)
        for i in range(max_len):
            votes = Counter(p[i] for p in paths if i < len(p))
            if not votes:
                continue
            top, _ = votes.most_common(1)[0]
            if i < len(steps):
                if votes[top] > votes.get(steps[i], 0):
                    steps[i] = top
            else:
                steps.append(top)

    # Graft unique better/fix hints that look actionable.
    existing = " ".join(steps).lower()
    for ep in eps:
        for c in critique_items(ep):
            if not isinstance(c, dict):
                continue
            if slot_of(str(c.get("mode") or "")) != slot:
                continue
            for key in ("better", "fix"):
                hint = str(c.get(key) or "").strip()
                if not hint:
                    continue
                # Skip if already covered by a step.
                hint_toks = tokens(hint)
                if hint_toks and any(
                    jaccard(hint_toks, tokens(s)) >= 0.5 for s in steps
                ):
                    continue
                if hint.lower() in existing:
                    continue
                steps.append(hint)
                existing = " ".join(steps).lower()

    # Cap 6; keep at least what's there for incomplete marking.
    return steps[:6]


def avoid_bullets(eps: list[dict], slot: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for ep in eps:
        for c in critique_items(ep):
            if not isinstance(c, dict):
                continue
            if slot_of(str(c.get("mode") or "")) != slot:
                continue
            cost = str(c.get("cost") or "").strip()
            if cost and cost not in seen:
                seen.add(cost)
                out.append(cost)
    return out[:6]


def when_hint(eps: list[dict]) -> str:
    tasks = [str(ep.get("task") or "").strip() for ep in eps if str(ep.get("task") or "").strip()]
    if not tasks:
        return "manual select; no alias yet"
    # Repeated short phrases — otherwise manual.
    if len(tasks) == 1:
        return f"{tasks[0]} — manual select until an alias + CASES negative row exist"
    return (
        " / ".join(tasks[:3])
        + " — manual select until an alias + CASES negative row exist"
    )


def mark_incomplete(slot: str, steps: list[str]) -> bool:
    n = len(steps)
    if n < 2 or n > 6:
        return True
    if slot in LIFECYCLE_SLOTS and path_missing_auth_lifecycle(steps):
        return True
    concrete_n = sum(1 for s in steps if CONCRETE.search(s))
    if concrete_n < (n + 1) // 2:  # fewer than half (ceil)
        return True
    return False


def fm_list(ids: list[str]) -> str:
    return "[" + ", ".join(ids) + "]"


def render_draft(
    slot: str,
    kind: str,
    cluster_label: str,
    eps: list[dict],
    steps: list[str],
    avoids: list[str],
    incomplete: bool,
) -> str:
    eids = [str(ep.get("id") or "") for ep in eps if ep.get("id")]
    title = SLOT_DESC.get(slot, slot).split("：")[0].split(":")[0].strip() or slot
    lines = [
        "---",
        "status: draft",
        f"slot: {slot}",
        f"kind: {kind}",
        f"source_episodes: {fm_list(eids)}",
        f"cluster: {cluster_label}",
        f"incomplete: {'true' if incomplete else 'false'}",
        "---",
        "",
        f"# {title}",
        "",
        SLOT_DESC.get(slot, ""),
        "",
        "## When",
        "",
        when_hint(eps),
        "",
        "## Steps",
        "",
    ]
    if steps:
        for i, s in enumerate(steps, 1):
            lines.append(f"{i}. {s}")
    else:
        lines.append("1. TODO")
    lines.extend(["", "## Avoid", ""])
    if avoids:
        for a in avoids:
            lines.append(f"- {a}")
    else:
        lines.append("- TODO")
    lines.extend(["", "## Sources", ""])
    for ep in eps:
        eid = ep.get("id") or "?"
        task = str(ep.get("task") or "").strip() or "(no task)"
        # one-line
        task = re.sub(r"\s+", " ", task)[:120]
        lines.append(f"- `{eid}` — {task}")
    lines.append("")
    return "\n".join(lines)


def write_draft(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--json-only"]
    json_only = "--json-only" in sys.argv[1:]
    root = Path(args[0] if args else traces_dir())
    drafts_dir = root / "playbooks" / "_drafts"

    # slot -> set of episode ids (≤1 per episode); keep first ep object per id
    slot_eps: dict[str, dict[str, dict]] = defaultdict(dict)
    raw_modes: dict[str, Counter[str]] = defaultdict(Counter)
    advice: dict[str, list[str]] = defaultdict(list)
    auth_gaps: list[str] = []

    eps = [e for e in load_episodes(root) if isinstance(e, dict)]
    for ep in eps:
        eid = str(ep.get("id") or "").strip()
        if path_missing_auth_lifecycle(ep.get("preferred_path") or []):
            if eid:
                auth_gaps.append(eid)
        seen_slots: set[str] = set()
        for c in critique_items(ep):
            if not isinstance(c, dict):
                continue
            mode = str(c.get("mode") or "").strip()
            if not mode:
                continue
            slot = slot_of(mode)
            raw_modes[slot][mode[:60]] += 1
            for key in ("better", "fix", "note"):
                text = str(c.get(key) or "").strip()
                if text:
                    advice[slot].append(text[:120])
                    break
            if eid and slot not in seen_slots:
                seen_slots.add(slot)
                slot_eps[slot][eid] = ep

    slot_counts = {s: len(ids) for s, ids in slot_eps.items()}
    ripe_slots = [
        s for s, n in slot_counts.items()
        if n >= threshold_for(s) and s != UNCLASSIFIED
    ]

    draft_paths: list[str] = []
    distill_rows: list[dict] = []

    # Iterate by count desc for stable summary ordering
    for slot, count in sorted(slot_counts.items(), key=lambda x: (-x[1], x[0])):
        ep_list = list(slot_eps[slot].values())
        kind = kind_for(slot, ep_list) if count >= threshold_for(slot) and slot != UNCLASSIFIED else "avoid"
        row = {
            "slot": slot,
            "means": SLOT_DESC.get(slot, "未归类，请补 modes.py 的关键词"),
            "count": count,
            "threshold": threshold_for(slot),
            "raw_modes": raw_modes[slot].most_common(6),
            "episodes": list(slot_eps[slot].keys())[:8],
            "advice_seen": advice[slot][:3],
            "kind": kind if slot in ripe_slots else None,
            "action": action_for(slot, count, kind if slot in ripe_slots else "avoid"),
            "drafts": [],
        }

        if slot in ripe_slots and kind == "playbook":
            clusters = cluster_episodes(ep_list, slot)
            # Drop clusters that do not meet threshold (except multi-cluster lifecycle)
            kept: list[tuple[str, list[dict]]] = []
            multi = len(clusters) >= 2
            letters = "abcdefghijklmnopqrstuvwxyz"
            for idx, cluster in enumerate(clusters):
                c_count = len(cluster)
                if c_count >= threshold_for(slot) or (multi and slot in LIFECYCLE_SLOTS and c_count >= 1):
                    label = "default" if not multi else letters[idx] if idx < len(letters) else f"c{idx}"
                    kept.append((label, cluster))
            if not kept and clusters:
                # Fallback: merge all (should be rare)
                kept = [("default", ep_list)]

            for label, cluster in kept:
                steps = vote_steps(cluster, slot)
                avoids = avoid_bullets(cluster, slot)
                incomplete = mark_incomplete(slot, steps)
                stem = slot if label == "default" else f"{slot}-{label}"
                path = drafts_dir / f"{stem}.md"
                body = render_draft(slot, kind, label, cluster, steps, avoids, incomplete)
                write_draft(path, body)
                draft_paths.append(str(path))
                row["drafts"].append(str(path))

        distill_rows.append(row)

    summary = {
        "episodes": len(eps),
        "slots_total": len(slot_counts),
        "ripe_for_distill": len(ripe_slots),
        "threshold_default": THRESHOLD,
        "threshold_lifecycle": 1,
        "lifecycle_slots": sorted(LIFECYCLE_SLOTS),
        "auth_path_gaps": {
            "count": len(auth_gaps),
            "hint": "preferred_path 含推/令牌但缺失败问/本机存 — 蒸馏时补生命周期",
            "examples": auth_gaps[:8],
        },
        "drafts_written": draft_paths,
        "distill": distill_rows[:20],
    }
    # Human-friendly: indent unless --json-only (still indented; flag reserved)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if json_only:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
