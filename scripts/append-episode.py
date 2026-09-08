#!/usr/bin/env python3
"""Append one episode to today's jsonl with hard checks (retrieved + preferred_path).

Usage:
  python3 scripts/append-episode.py <<'EOF'
  { ... episode json ... }
  EOF

  python3 scripts/append-episode.py path/to/ep.json

Exit 2 = validation failed (nothing written).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modes import SLOT_NAMES, UNCLASSIFIED, looks_like_prose, slot_of  # noqa: E402
from paths import traces_dir_for_write  # noqa: E402
from quality import (  # noqa: E402
    SECRET_HYGIENE_BETTER,
    discard_secret_without_store,
    is_junk,
    is_thin,
    path_missing_auth_lifecycle,
    why_thin,
)

TZ = timezone(timedelta(hours=8))


def fail(msg: str) -> int:
    print(f"append-episode: {msg}", file=sys.stderr)
    return 2


def validate(ep: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(ep, dict):
        return ["episode must be a JSON object"]

    if not str(ep.get("id") or "").strip():
        errs.append("missing id")
    if not str(ep.get("task") or "").strip():
        errs.append("missing task")

    pp = ep.get("preferred_path")
    if not isinstance(pp, list) or not any(str(x).strip() for x in pp):
        errs.append("preferred_path must be a non-empty list (2–6 short steps)")

    if "retrieved" not in ep:
        errs.append("missing retrieved (use [] if novel / no hit)")
    else:
        retrieved = ep.get("retrieved")
        if not isinstance(retrieved, list):
            errs.append("retrieved must be a list")
        else:
            for i, r in enumerate(retrieved):
                if not isinstance(r, dict):
                    errs.append(f"retrieved[{i}] must be object")
                    continue
                if not str(r.get("id") or "").strip():
                    errs.append(f"retrieved[{i}].id required")
                if "score" not in r:
                    errs.append(f"retrieved[{i}].score required")
                if "used" not in r or not isinstance(r.get("used"), bool):
                    errs.append(f"retrieved[{i}].used must be bool")

    outcome = ep.get("outcome")
    if outcome is not None and not isinstance(outcome, dict):
        errs.append("outcome must be object when present")
    elif isinstance(outcome, dict) and "ok" not in outcome:
        errs.append("outcome.ok required when outcome present")

    for i, d in enumerate(ep.get("decisions") or []):
        if not isinstance(d, dict):
            errs.append(f"decisions[{i}] must be object")
            continue
        opts = d.get("options")
        if opts is not None and (not isinstance(opts, list) or len(opts) < 2):
            errs.append(f"decisions[{i}].options should list ≥2 alternatives")

    return errs


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0

    if len(sys.argv) > 1:
        raw = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()

    if not raw.strip():
        return fail("empty input")

    try:
        ep = json.loads(raw)
    except json.JSONDecodeError as e:
        return fail(f"invalid JSON: {e}")

    errs = validate(ep)
    if errs:
        return fail("; ".join(errs))

    if is_junk(ep) and "--force" not in sys.argv:
        return fail(f"junk episode (非任务记录且无信号)：{why_thin(ep)}。确实要留用 --force")
    if is_thin(ep):
        print(f"append-episode: WARN thin episode — {why_thin(ep)}", file=sys.stderr)

    if isinstance(ep.get("critique"), dict):
        ep["critique"] = [ep["critique"]]

    for c in ep.get("critique") or []:
        if not isinstance(c, dict):
            continue
        mode = str(c.get("mode") or "").strip()
        if not mode:
            continue
        slot = slot_of(mode)
        if looks_like_prose(mode):
            print(
                f"append-episode: WARN mode 写成了散文（{len(mode)} 字），"
                f"精确计数永远不会重复 → 蒸馏不触发。请用槽位名并把细节移到 better/fix。"
                f"推断槽位={slot}；可选：{', '.join(SLOT_NAMES)}",
                file=sys.stderr,
            )
        elif slot == UNCLASSIFIED:
            print(
                f"append-episode: WARN mode「{mode}」归不到任何槽位，"
                f"蒸馏时会被单独计数。补 modes.py 的关键词，或改用：{', '.join(SLOT_NAMES)}",
                file=sys.stderr,
            )
        better = str(c.get("better") or c.get("fix") or c.get("note") or "")
        if slot == "secret_hygiene" and discard_secret_without_store(better):
            c["better"] = SECRET_HYGIENE_BETTER
            print(
                "append-episode: WARN secret_hygiene 写成了「用完即弃」且无本机存储；"
                f"已改写 better → {SECRET_HYGIENE_BETTER}",
                file=sys.stderr,
            )

    if path_missing_auth_lifecycle(ep.get("preferred_path") or []):
        print(
            "append-episode: WARN preferred_path 含推/令牌但缺失败问 token / 本机存复用；"
            "闭环应含：失败问→save 覆盖→下次 push 读本地",
            file=sys.stderr,
        )

    now = datetime.now(TZ)
    ep.setdefault("at", now.isoformat(timespec="seconds"))
    ep.setdefault("constraints", [])
    ep.setdefault("decisions", [])
    ep.setdefault("outcome", {"ok": True, "tests": ""})
    ep.setdefault("bad_case", False)
    ep.setdefault("critique", [])
    ep.setdefault("reward_hints", [])
    for dead in ("steps", "plan", "system_update"):
        ep.pop(dead, None)

    traces = traces_dir_for_write()
    traces.mkdir(parents=True, exist_ok=True)
    day = traces / f"{now.date().isoformat()}.jsonl"
    line = json.dumps(ep, ensure_ascii=False) + "\n"
    with day.open("a", encoding="utf-8") as f:
        f.write(line)

    if ep.get("bad_case") or ep.get("critique"):
        bad = traces / "bad-cases.jsonl"
        with bad.open("a", encoding="utf-8") as f:
            f.write(line)

    used = sum(
        1
        for r in (ep.get("retrieved") or [])
        if isinstance(r, dict) and r.get("used") is True
    )
    print(json.dumps({
        "ok": True,
        "path": str(day),
        "id": ep.get("id"),
        "retrieved_n": len(ep.get("retrieved") or []),
        "retrieved_used": used,
        "preferred_path_n": len(ep.get("preferred_path") or []),
        "critique_slots": [
            slot_of(str(c.get("mode") or ""))
            for c in (ep.get("critique") or [])
            if isinstance(c, dict) and str(c.get("mode") or "").strip()
        ],
        "bad_case_mirrored": bool(ep.get("bad_case") or ep.get("critique")),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
