# Design

pathbook is a **distillation pipeline**, not a memory database. Vector search is the weaker half; the product is promoting traces into preferences and playbooks.

It is **not** fine-tuning and **not** gradient RL. Say “procedural memory” / “context engineering”.

## What it can and cannot do

| Can | Cannot |
|---|---|
| Stop the same job being implemented differently each time | Give the model a skill it never had |
| Skip re-planning on a known task | Replace domain training data |
| Turn a pitfall into an `avoid` hint | Guarantee first-try correctness |

## Three layers

```
preferences   keyword inject, always on     tool choices     ~20 tokens
playbooks     alias → zero planning         SOPs             ~200 tokens
episodes      similarity × trust            long tail        ~few hundred tokens
```

The promotion pipe (episode → playbook / preference) is the system. Storage is not.

Retrieval rank: `score = similarity × (0.5 + trust)`. Trust is derived from later traces; unproven items keep coefficient 1.0.

## Metrics that matter

Do not report “hit rate” (that is potential). Report:

- turns to finish a repeated task
- retry / undo rate
- tokens per task
- `retrieved.used` among all episodes
- playbook count

Leave-one-out only. Scoring a corpus against itself includes the query’s own episode and inflates reuse.

## Known failure modes

- **Self-report bias.** Models mark `outcome.ok: true` by default. Trust is only as good as honest `used` flags.
- **False reuse.** A shared word like “效果” can clear 0.30 and skip planning on the wrong SOP. Check task domain, not just score.
- **Wide aliases.** Bare `push` / `推送` steals novel requests (“can we open-source this”). Imperative + object, then add a negative `CASES` row.
- **Stale SOPs.** After a toolchain change, an old playbook is worse than none. Bind playbooks to a source fingerprint when you can; `hit-report` dead aliases and rising failure after reuse are the cheap signals.
- **Discard-only secrets.** Distilling “throw the token away” blocks the local overwrite store. The retriever rewrites that lesson on the way out.

## Related work

- [Trace2Skill](https://arxiv.org/html/2603.25158v2) — static distilled skills beat test-time memory banks; skills transfer across model families.
- [Memp](https://aclanthology.org/2026.findings-acl.866.pdf) — procedural memory needs Build / Retrieve / Update+Deprecate.
- [TencentDB Agent Memory](https://github.com/tencent/tencentdb-agent-memory) — storage + ACL + mixed retrieval is a crowded layer. Differentiate on capture, ground-truth, and deprecation.

Single-user writing cost is high; the economics flip when many people do overlapping work and one playbook is shared.
