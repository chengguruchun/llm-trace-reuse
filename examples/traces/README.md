# Sample traces

Synthetic episodes and playbooks so `route.py` / `eval-loo.py` have something to read in this repository.

Copy `preferences.md` and `playbooks/` into **your** `$LLM_TRACE_REUSE_HOME` (default `.llm-trace-reuse/`) and edit them. `playbooks/_drafts/` is machine-writable; `route.py` ignores `_` directories until `promote-playbook.py` moves a draft to `playbooks/*.md`.

Do not commit real traces. `append-episode.py` writes to `.llm-trace-reuse/`, which is gitignored.
