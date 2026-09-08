# llm-trace-reuse

**Procedural memory for coding agents.** Route a request to a playbook, reuse a past `preferred_path`, or fall through to the model — then record the decision chain so the next similar request does not start from zero.

This is **not** gradient RL. It does not update model weights. It is retrieval + distillation: preferences, playbooks, and episodes.

[中文说明](#中文)

## What it is

```
preferences   always-on tool choices     (~20 tokens each)
playbooks     alias → skip planning      (SOPs)
episodes      retrieve × trust           (long tail)
      ↓ same critique slot ≥ 2
   shorter playbook / script
```

Score: `similarity × (0.5 + trust)`. Similarity is IDF-weighted **query coverage** (long write-ups are not punished). Trust is Laplace-smoothed from later `retrieved[].used` plus that turn's `outcome.ok`. Unproven episodes rank exactly as before.

## Install (Cursor)

The repo root **is** a Cursor skill (`SKILL.md` + `scripts/`).

```bash
git clone https://github.com/chengguruchun/llm-trace-reuse.git
ln -s "$(pwd)/llm-trace-reuse" /path/to/your-project/.cursor/skills/llm-trace-reuse
```

Create a gitignored home for *your* traces (never commit real episodes):

```bash
mkdir -p /path/to/your-project/.llm-trace-reuse/playbooks
# copy the example files and edit them
cp llm-trace-reuse/examples/traces/preferences.md /path/to/your-project/.llm-trace-reuse/
```

Optional: copy `rules/llm-trace-reuse.mdc` into `.cursor/rules/` so the agent routes at the start of every task.

Override locations with `LLM_TRACE_REUSE_HOME` (traces) and `LLM_TRACE_REUSE_ROOT` (project root).

## Use

```bash
# start of a task
python3 scripts/route.py "把代码推到远端"

# end of a task (rejected unless retrieved + preferred_path are present)
python3 scripts/append-episode.py <<'EOF'
{
  "id": "2026-01-02-short-slug",
  "task": "user intent",
  "retrieved": [],
  "preferred_path": ["step 1", "step 2"],
  "decisions": [],
  "outcome": {"ok": true, "tests": ""}
}
EOF

python3 scripts/eval-loo.py
python3 scripts/hit-report.py
python3 scripts/distill.py
python3 scripts/redact-check.py --publish
python3 scripts/test-aliases.py
```

| route | model |
|---|---|
| `playbook` / `script` | skip planning; run the SOP |
| `reuse` | skip planning; run `preferred_path` |
| `llm` | think; inject only a short path, never the jsonl |

Every route also emits `preferences` (keyword-matched habits) and `avoid` (past lessons). Fill `retrieved[].used` honestly — that is the only signal that moves trust.

## What is in this repo

| Include | Leave out |
|---|---|
| Router, retriever, append gate, eval, distill, redact, alias tests | Anyone's real traces |
| Synthetic `examples/traces/*` | Product / infra / business code |
| Generic playbooks (git push, run tests) | Internal hosts, tokens, RFC1918 addresses |

`redact-check.py --publish` is the gate: secrets always fail; private-network IPs fail only with `--publish`.

## Name

**llm-trace-reuse**: record LLM-agent traces, retrieve similar ones, reuse the `preferred_path`. The useful artifact is a short executable path, not a memory dump.

## License

MIT. See [LICENSE](LICENSE).

---

## 中文

给编程助手用的**过程性记忆**：先路由，能走手册就走手册；能复用上次的 `preferred_path` 就不要重新规划；反复踩的坑蒸馏成更短的脚本。

不是真·强化学习，改不了模型权重。

本仓库只开源引擎和合成示例。真实轨迹、业务代码、内网地址不要放进来。
