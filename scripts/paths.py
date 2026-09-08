#!/usr/bin/env python3
"""Resolve the traces home. No hardcoded product or company paths.

Read order:
  1. LLM_TRACE_REUSE_HOME
  2. <project>/.llm-trace-reuse  if that directory exists
  3. bundled examples/traces (this repo only)
  4. <project>/.llm-trace-reuse  (created on first write)

Write always goes to LLM_TRACE_REUSE_HOME or <project>/.llm-trace-reuse —
never into the bundled examples, so sample data stays clean.
"""
from __future__ import annotations

import os
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
EXAMPLES = REPO / "examples" / "traces"
SKILL_NAME = "llm-trace-reuse"
TRACES_DIRNAME = ".llm-trace-reuse"


def project_root(start: Path | None = None) -> Path:
    env = os.environ.get("LLM_TRACE_REUSE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / TRACES_DIRNAME).is_dir():
            return p
        if (p / ".cursor" / "skills" / SKILL_NAME / "SKILL.md").is_file():
            return p
        if (p / "SKILL.md").is_file() and (p / "scripts" / "route.py").is_file():
            return p
    return cur


def traces_dir(start: Path | None = None) -> Path:
    env = os.environ.get("LLM_TRACE_REUSE_HOME")
    if env:
        return Path(env).expanduser().resolve()
    root = project_root(start)
    local = root / TRACES_DIRNAME
    if local.is_dir():
        return local
    if EXAMPLES.is_dir() and (EXAMPLES / "preferences.md").is_file():
        return EXAMPLES
    return local


def traces_dir_for_write(start: Path | None = None) -> Path:
    env = os.environ.get("LLM_TRACE_REUSE_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return project_root(start) / TRACES_DIRNAME
