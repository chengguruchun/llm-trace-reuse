---
name: pathbook
description: >-
  Procedural memory for coding agents. Route to playbook / reuse / llm, record
  episodes, distill repeated failures. Triggers: pathbook, playbook, preferred_path,
  episode, distill, eval-loo, 复盘, 决策复用. Skip only if the user says 这次不记.
---

# pathbook

Local files, not the git history of the host project. This is **not** gradient RL.

## Start (route first)

```bash
python3 .cursor/skills/pathbook/scripts/route.py "<user text>"
```

| route | model |
|---|---|
| `playbook` / `script` | skip planning; run the SOP |
| `reuse` | skip planning; run `preferred_path`; model only on failure |
| `llm` | novel task; inject a short path, never the jsonl |

Honor `preferences` and `avoid` on every route.

- Preferences live in `$PATHBOOK_HOME/preferences.md` (default `.pathbook/preferences.md`).
- Add a domain with `## Name` + `触发：keywords` + `- items`. Re-run `test-aliases.py`.
- Prefer a new preference (~20 tokens, always on) over a new episode (~400 tokens, maybe retrieved).

Score: `similarity × (0.5 + trust)`. Trust comes from later `retrieved[].used` + `outcome.ok` (Laplace, 0.5 = unproven). **Fill `used` honestly.**

Do not write `steps` / `plan` / `system_update`. Nothing reads them.

## During (the whole decision chain)

Record every fork, including the roads not taken:

```json
{
  "point": "git.remote",
  "context": "user said push yesterday's work",
  "options": ["origin", "another remote they did not name"],
  "choice": "origin",
  "reason": "default remote + retrieve hit",
  "reused_from": "2026-01-01-git-push-ok"
}
```

## End (append)

```bash
python3 .cursor/skills/pathbook/scripts/append-episode.py <<'EOF'
{
  "id": "2026-01-02-short-slug",
  "task": "user intent",
  "retrieved": [{"id": "…", "score": 0.2, "used": true}],
  "preferred_path": ["step1", "step2"],
  "decisions": [],
  "outcome": {"ok": true, "tests": "", "user_feedback": ""}
}
EOF
```

`retrieved` is required (`[]` if novel). Each hit needs `score` + `used`. `preferred_path` must be non-empty. `bad_case` or a non-empty `critique` is mirrored to `bad-cases.jsonl`.

## critique

```json
"critique": [{"mode": "false_positive", "cost": "two extra rounds", "better": "what to do instead"}]
```

1. Must be an **array**. A dict is iterated as keys and poisons the index with `"mode"` / `"fix"`.
2. `mode` must be a slot from `modes.py` (`python3 scripts/modes.py`). Prose never repeats, so distill never fires.
3. Put the advice in `cost` / `better` / `fix`.

Also:

- `secret_hygiene` ≠ discard-after-use. Ban plaintext in URLs/chat; allow `.pathbook/secrets` overwrite.
- `preferred_path` must include the failure branch and where to read the token next time.

Same slot ≥2 → a **shorter** playbook/script, not a longer always-on rule.

Weekly: `eval-loo.py`. Routing health: `hit-report.py [--verbose]`.

| metric | use |
|---|---|
| `alias.dead_aliases` | rule written, nobody talks that way → retune or delete |
| `threshold_sweep` + `marginal_hits` | raise the threshold only if the pairs are wrong-topic |
| `dead_stock` | unused ≠ useless; do not delete from this number |
| `avoid_supply.pct` | low → write more critiques, or they do not match queries |
| `corpus_quality.junk` | `>0` → `prune-junk.py --apply` |

After changing an alias regex, run `test-aliases.py`. Add a `CASES` row for every new false hit **before** loosening the regex.

`prune-junk.py` is dry-run by default; `--apply` moves rows to `_pruned/` (isolated, not deleted).

```bash
python3 scripts/redact-check.py            # SECRET fails
python3 scripts/redact-check.py --publish  # RFC1918 also fails
```

Built-in aliases: git-push, run-tests, distill, retrieve, eval-loo. Add project SOPs as local playbooks, not by forking this file with product names.

Write an episode for every task unless the user says 这次不记.
