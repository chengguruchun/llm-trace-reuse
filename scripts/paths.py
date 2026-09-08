#!/usr/bin/env python3
"""Resolve the traces home. No hardcoded product or company paths.

Read order:
  1. PATHBOOK_HOME
  2. <project>/.pathbook  if that directory exists
  3. bundled examples/traces (this repo only)
  4. <project>/.pathbook  (created on first write)

Write always goes to PATHBOOK_HOME or <project>/.pathbook — never into
the bundled examples, so sample data stays clean.
"""
from __future__ import annotations

import os
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
EXAMPLES = REPO / "examples" / "traces"


def project_root(start: Path | None = None) -> Path:
    env = os.environ.get("PATHBOOK_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / ".pathbook").is_dir():
            return p
        if (p / ".cursor" / "skills" / "pathbook" / "SKILL.md").is_file():
            return p
        if (p / "SKILL.md").is_file() and (p / "scripts" / "route.py").is_file():
            return p
    return cur


def traces_dir(start: Path | None = None) -> Path:
    env = os.environ.get("PATHBOOK_HOME")
    if env:
        return Path(env).expanduser().resolve()
    root = project_root(start)
    local = root / ".pathbook"
    if local.is_dir():
        return local
    if EXAMPLES.is_dir() and (EXAMPLES / "preferences.md").is_file():
        return EXAMPLES
    return local


def traces_dir_for_write(start: Path | None = None) -> Path:
    env = os.environ.get("PATHBOOK_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return project_root(start) / ".pathbook"
