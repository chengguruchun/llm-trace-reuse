# Preferences

Only tool choices and habits — never step-by-step SOPs. Those belong in playbooks.

Format: `## Domain` + `触发：space-separated keywords` + `- items`.

`route.py` injects a matching section on every route, including `llm`.

## Browser

触发：browser 浏览器 screenshot 截图 页面

- Use the user's already-open browser. Do not launch a new headless window.
- If the browser MCP is disconnected, stop and ask the user to connect it.
- Start with a snapshot so you know which page you are on.

## Tests

触发：test 测试 回归 pytest

- Run the project's filtered test command, not a full unbounded suite.
- Give the command enough time. Report pass count and duration.
- A green compile is not a test.

## Logs

触发：日志 log 报错

- Read log files with a file tool. Do not page through `tail` in the shell.
- Confirm the process or container is actually running before digging.

## Git push

触发：git-push 推远端 推到远端 推上去 推一下 远端 PAT

- On auth failure, ask the user for a token immediately. Do not guess from old chat.
- Save the token to `.llm-trace-reuse/secrets/git.pat` (overwrite). Next push reads that file.
- Never put a token in a remote URL, a commit, or an episode body.

## Distill

触发：蒸馏 distill critique preferred_path

- `preferred_path` must include the failure branch and where to read secrets next time.
- `secret_hygiene` forbids plaintext in URLs/chat; it does **not** forbid a local overwrite store.
- Same critique slot ≥2 times → a shorter playbook or script, not a longer always-on rule.
