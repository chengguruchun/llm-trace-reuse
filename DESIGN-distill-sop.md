# Distill → executable SOP

Companion to [DESIGN.md](DESIGN.md). Distillation’s **done state** is a short playbook the router can run — not a JSON note that says “go write a playbook”.

This document is the contract for the first implementation cut. Trace text is concatenated / voted into steps (no LLM polish by default).

## Pipeline

```
critique.mode (slot enum)
    → per-episode slot counts
    → kind: playbook | preference | avoid
    → cluster within slot (preferred_path / better)
    → playbooks/_drafts/*.md     # machine-writable; route ignores
    → promote-playbook           # quality gate
    → playbooks/*.md             # active; alias optional, explicit
```

| Stage | Who writes | Route reads? |
|---|---|---|
| `_drafts/` | `distill.py` | **No** (name starts with `_`, same isolation idea as retrieve) |
| `playbooks/*.md` | `promote-playbook.py` after checks | **Yes** |
| `preferences.md` | distill may *suggest*; human/agent appends | Yes (always-on keywords) |

## Append intake (signal quality)

Before an episode is worth distilling, `critique.mode` must be aggregable:

1. Non-empty `mode` that `looks_like_prose` **or** maps to `unclassified` → **reject** append (exit 2), unless `--force`.
2. Detail belongs in `better` / `fix` / `cost`, not in `mode`.
3. If `slot_of(mode)` hits a real slot and `mode` is not already the slot name → normalize `mode` to the slot name (optional `mode_raw`).

Historical jsonl is left alone; only new writes are strict.

## Counting and thresholds

- Count **per episode per slot** (each `id` contributes ≤1), not per critique row.
- Ignore `unclassified` for ripeness.
- Default threshold: **2** episodes.
- High-risk lifecycle slots `secret_hygiene`, `stale_creds`: threshold **1**.

## Kind: playbook vs preference vs avoid

Not every ripe slot becomes a playbook.

| kind | When | Artifact |
|---|---|---|
| `playbook` | Stable steps + clear failure branch (e.g. `stale_creds`, `env_setup`) | `_drafts/*.md` |
| `preference` | One-line always-on habit (~20 tokens) | Suggest a bullet for `preferences.md`; do not invent a SOP |
| `avoid` | “Don’t do X” without a reusable happy path (e.g. some `premature_claim`, `metric_misuse`) | Short avoid card in draft body or distill JSON; no alias |

Heuristic (v1, deterministic):

- Lifecycle slots → always `playbook`.
- If merged `preferred_path` has ≥2 concrete steps → `playbook`.
- Else if lessons are short and always-on → `preference`.
- Else → `avoid`.

## Clustering (one slot ≠ one SOP)

Within a ripe playbook slot, cluster source episodes by Jaccard similarity on:

- tokenized `preferred_path` joined, and/or
- `better`/`fix` text

If two clusters both meet the slot threshold (or lifecycle threshold 1 with distinct paths), emit **two** draft files (`{slot}-a.md`, `{slot}-b.md`). Prefer two short SOPs over one mash-up.

## Draft markdown template

Frontmatter + body. Steps are **trace-derived only** (vote / align `preferred_path`, graft failure hints from `better`/`fix`). Mark gaps `TODO` — do not invent commands.

```markdown
---
status: draft
slot: stale_creds
kind: playbook
source_episodes: [2026-01-01-git-push-stale, 2026-01-01-secret-hygiene]
cluster: default
incomplete: false
---

# {short title}

{SLOT_DESC}

## When

{narrow trigger hints from repeated task phrases — or “manual select; no alias yet”}

## Steps

1. …
2. …
3. …   # failure branch required for lifecycle slots

## Avoid

- …

## Sources

- `episode-id` — one-line task
```

`incomplete: true` when:

- fewer than 2 or more than 6 steps after assembly, or
- lifecycle slot and `path_missing_auth_lifecycle(steps)` would be true, or
- fewer than half the steps look concrete (reuse `quality.CONCRETE`).

Incomplete drafts are still written (so humans see the gap) but **must fail promote**.

## Promotion gate

`promote-playbook.py path/to/draft.md`:

| Check | Rule |
|---|---|
| status | must be `draft` |
| incomplete | must be false / absent |
| steps | 2–6 |
| concrete | ≥ half match `CONCRETE` |
| lifecycle | if slot ∈ {secret_hygiene, stale_creds}, failure→ask→local store→retry must be present |
| secrets | body must pass the same SECRET scan as `redact-check` (no literal tokens) |

On success: write `playbooks/{name}.md` with `status: active`, remove or archive the draft, print checklist:

1. Add / tighten alias (imperative + object).
2. Add a `CASES` negative row before widening the trigger.
3. Do **not** auto-edit alias regexes in v1.

## Router contract

- Load playbooks from `playbooks/*.md` only — never `_drafts/`, never `_*` directories.
- Active SOP with no alias → reachable only via explicit reuse / manual mention; that is OK for fresh promotes.

## Metrics (optimize these)

Do not optimize draft count or raw slot hits. Track:

- **promotion rate**: drafts that pass promote / drafts written
- **rounds saved**: repeated tasks that took fewer turns after an active SOP existed
- **post-promote failure rate**: `outcome.ok=false` after `route=playbook` for that SOP (stale signal)

## Out of scope for the first cut

- LLM `--polish` on step text
- Playbook source fingerprints / auto-deprecate
- False-reuse domain validation at retrieve time
- Expanded secret patterns (separate hardening track)

## Acceptance for the first PR

1. Append rejects prose / unclassified `mode` without `--force`.
2. `distill.py` writes `_drafts` for ripe playbook slots from synthetic / example traces.
3. `promote-playbook.py` accepts the gold sample shape and rejects incomplete drafts.
4. Tests cover the above; `redact-check.py --publish` still clean.
