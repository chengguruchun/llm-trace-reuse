#!/usr/bin/env python3
"""Promote a playbooks/_drafts/*.md draft to an active playbook after quality gates.

Usage:
  python3 scripts/promote-playbook.py path/to/draft.md

On success: writes playbooks/{stem}.md with status: active, moves the draft away,
prints an alias + CASES checklist. Exit nonzero on failure. Never prints secrets.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modes import SLOT_NAMES  # noqa: E402
from quality import CONCRETE, path_missing_auth_lifecycle  # noqa: E402

LIFECYCLE_SLOTS = frozenset({"secret_hygiene", "stale_creds"})

# Same patterns as redact-check.SECRET (hyphenated module is not importable).
SECRET = [
    re.compile(r"glpat-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgho_[A-Za-z0-9]{20,}"),
    # Value must contain a digit so English prose after "token" + colon is not a hit.
    re.compile(
        r"(?i)(password|passwd|secret|token|authorization)\s*[:=]\s*"
        r"[\"']?(?!\$)(?=[A-Za-z0-9_\-+/=]*\d)[A-Za-z0-9_\-+/=]{8,}"
    ),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"-P[\s\"',]+[\"'][^\"']{4,}[\"']"),
]


def fail(msg: str) -> int:
    print(f"promote-playbook: {msg}", file=sys.stderr)
    return 2


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    block = text[3:end].strip("\n")
    body = text[end + 4:].lstrip("\n")
    meta: dict = {}
    for line in block.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            items = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
            meta[key] = items
        elif raw.lower() in ("true", "false"):
            meta[key] = raw.lower() == "true"
        else:
            meta[key] = raw
    return meta, body


def section_body(body: str, heading: str) -> str:
    """Return text under `## {heading}` until the next ## or EOF."""
    pat = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.M | re.I)
    m = pat.search(body)
    if not m:
        return ""
    start = m.end()
    nxt = re.search(r"^##\s+", body[start:], re.M)
    end = start + nxt.start() if nxt else len(body)
    return body[start:end].strip()


def parse_steps(section: str) -> list[str]:
    steps = []
    for line in section.splitlines():
        m = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if m:
            steps.append(m.group(1).strip())
    return steps


def parse_avoid(section: str) -> list[str]:
    items = []
    for line in section.splitlines():
        m = re.match(r"^\s*-\s+(.+)$", line)
        if m:
            items.append(m.group(1).strip())
    return items


def secret_hits(text: str) -> list[str]:
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        for pat in SECRET:
            m = pat.search(line)
            if m:
                # Do not echo the secret value — only line number + pattern family.
                hits.append(f"line {i}")
                break
    return hits


def promote(path: Path) -> int:
    if not path.is_file():
        return fail(f"not a file: {path}")
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)

    status = str(meta.get("status") or "").strip().lower()
    if status != "draft":
        return fail(f"status must be draft (got {status!r})")

    if meta.get("incomplete") is True:
        return fail("incomplete: true — fix steps before promote")

    slot = str(meta.get("slot") or "").strip()
    steps = parse_steps(section_body(body, "Steps"))
    _avoid = parse_avoid(section_body(body, "Avoid"))  # parsed for future checks

    n = len(steps)
    if n < 2 or n > 6:
        return fail(f"steps must be 2–6 (got {n})")

    concrete_n = sum(1 for s in steps if CONCRETE.search(s))
    if concrete_n * 2 < n:
        return fail(f"concrete steps {concrete_n}/{n} — need ≥ half matching CONCRETE")

    if slot in LIFECYCLE_SLOTS and path_missing_auth_lifecycle(steps):
        return fail(
            f"lifecycle slot {slot} missing failure→ask→local store→retry in Steps"
        )

    hits = secret_hits(text)
    if hits:
        return fail(f"secret-like content at {', '.join(hits)} — redact before promote")

    # Active path: same playbooks/ parent, not under _drafts
    playbooks_dir = path.parent
    if playbooks_dir.name == "_drafts":
        playbooks_dir = playbooks_dir.parent
    dest = playbooks_dir / path.name
    if dest.resolve() == path.resolve():
        return fail("draft is already outside _drafts; move it under _drafts first")

    # Rewrite frontmatter status → active
    active_meta = dict(meta)
    active_meta["status"] = "active"
    fm_lines = ["---"]
    for key in ("status", "slot", "kind", "source_episodes", "cluster", "incomplete"):
        if key not in active_meta:
            continue
        val = active_meta[key]
        if isinstance(val, list):
            fm_lines.append(f"{key}: [{', '.join(str(x) for x in val)}]")
        elif isinstance(val, bool):
            fm_lines.append(f"{key}: {'true' if val else 'false'}")
        else:
            fm_lines.append(f"{key}: {val}")
    for key, val in active_meta.items():
        if key in ("status", "slot", "kind", "source_episodes", "cluster", "incomplete"):
            continue
        fm_lines.append(f"{key}: {val}")
    fm_lines.append("---")
    active_text = "\n".join(fm_lines) + "\n\n" + body.lstrip("\n")
    if not active_text.endswith("\n"):
        active_text += "\n"

    playbooks_dir.mkdir(parents=True, exist_ok=True)
    dest.write_text(active_text, encoding="utf-8")
    try:
        path.unlink()
    except OSError as e:
        print(f"promote-playbook: WARN wrote {dest} but could not remove draft: {e}", file=sys.stderr)

    stem = dest.stem
    print(f"promoted → {dest}")
    print("checklist:")
    print(f"  1. Add / tighten alias for {stem!r} (imperative + object).")
    print("  2. Add a CASES negative row in scripts/test-aliases.py before widening the trigger.")
    print("  3. Do not auto-edit alias regexes in v1.")
    if slot and slot not in SLOT_NAMES:
        print(f"  note: slot {slot!r} is not in SLOT_NAMES — confirm modes.py", file=sys.stderr)
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(sys.argv) > 1 else 2
    return promote(Path(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
