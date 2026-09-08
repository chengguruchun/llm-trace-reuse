#!/usr/bin/env python3
"""Scan traces and skill sources for secrets / publish blockers.

  redact-check.py            # traces + scripts + docs
  redact-check.py --publish  # also fail on RFC1918 hosts (pre-open-source gate)

secret        -> always exit 1
publish-block -> exit 1 only with --publish
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from paths import REPO, traces_dir  # noqa: E402

SKIP_DIR_NAMES = {".git", "__pycache__", "_pruned", "_migrated-legacy", ".venv", "node_modules"}

SCAN = [
    (traces_dir(), ("*.jsonl", "*.md")),
    (REPO, ("*.py", "*.sh", "*.md", "*.yml", "*.yaml")),
]

SECRET = [
    re.compile(r"glpat-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgho_[A-Za-z0-9]{20,}"),
    # Literal assignment only. `token="${2:-}"` / `$TOKEN` must not match.
    re.compile(
        r"(?i)(password|passwd|secret|token|authorization)\s*[:=]\s*"
        r"[\"']?(?!\$)[A-Za-z0-9_\-+/=]{8,}"
    ),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"-P[\s\"',]+[\"'][^\"']{4,}[\"']"),
]

PUBLISH_BLOCK = [
    re.compile(r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"),
]

ALLOW = re.compile(
    r"(redact-check|PATHBOOK_|re\.(?:compile|search|match|finditer))"
)


def _skip(path: Path) -> bool:
    return any(p in SKIP_DIR_NAMES or p.startswith("_") for p in path.parts)


def scan_file(path: Path) -> tuple[list[str], list[str]]:
    secrets, blockers = [], []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return secrets, blockers
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip() or ALLOW.search(line):
            continue
        for pat in SECRET:
            m = pat.search(line)
            if m:
                secrets.append(f"{path}:{i}: {m.group(0)[:48]}")
                break
        for pat in PUBLISH_BLOCK:
            m = pat.search(line)
            if m:
                blockers.append(f"{path}:{i}: {m.group(0)[:48]}")
                break
    return secrets, blockers


def main() -> int:
    publish = "--publish" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    targets = [(Path(args[0]), ("*.jsonl", "*.md"))] if args else SCAN

    secrets: list[str] = []
    blockers: list[str] = []
    scanned = 0
    for root, globs in targets:
        if not root.exists():
            continue
        for pattern in globs:
            for path in sorted(root.rglob(pattern)):
                if _skip(path.relative_to(root)):
                    continue
                scanned += 1
                s, b = scan_file(path)
                secrets.extend(s)
                blockers.extend(b)

    for line in secrets:
        print(f"SECRET        {line}")
    for line in blockers:
        print(f"PUBLISH-BLOCK {line}")

    print(f"scanned {scanned} file(s): {len(secrets)} secret, {len(blockers)} publish-blocker")
    if secrets:
        print("FAIL: secret-like content must not be committed or published")
        return 1
    if blockers and publish:
        print("FAIL: private-network hosts block open-sourcing")
        return 1
    if blockers:
        print("ok (publish-blockers are fine locally; run --publish before open-sourcing)")
    else:
        print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
