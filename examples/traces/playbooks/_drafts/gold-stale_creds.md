---
status: draft
slot: stale_creds
kind: playbook
source_episodes: [2026-01-01-git-push-ok, 2026-01-01-git-push-stale, 2026-01-01-secret-hygiene]
cluster: git-auth
incomplete: false
---

# Git push when credentials went stale

凭证过期：失败即问用户；本机覆盖；下次复用（生命周期）。

## When

Same request as git push after an auth failure (推一下 / git push / 推到远端 + 认证失败 / Access denied / stale token).

Narrow: imperative + git remote. Do **not** alias bare `推送` / `push` alone (steals “can we open-source this”).

Manual select until an alias + CASES negative row exist.

## Steps

1. Confirm the current branch and the remote the user named (default `origin`). Do not invent a second remote.
2. If `.llm-trace-reuse/secrets/git.pat` exists, push with a throwaway `GIT_ASKPASS` that reads that file. Never put the token in the remote URL, the episode body, or chat.
3. On missing file or `Access denied` / auth failure: **stop**. Ask the user for a new token immediately. Do not retry the keychain in a loop. Do not guess a token from an old conversation.
4. When the user provides a token: overwrite `.llm-trace-reuse/secrets/git.pat`, then push again with the same ASKPASS path.
5. Record the episode with placeholders only (`preferred_path` may cite the secrets path; never the secret value). Fill `retrieved[].used` honestly.

## Avoid

- Empty keychain / credential-helper loops after the first auth failure.
- Pasting tokens into chat, URLs, commits, or jsonl.
- Teaching `secret_hygiene` as discard-after-use — local overwrite store is allowed; plaintext in URL/chat is not.
- Following an unrelated `preferred_path` just because a shared word scored above the reuse threshold.

## Sources

- `2026-01-01-git-push-ok` — 把当前分支推到远端（happy path + secrets path）
- `2026-01-01-git-push-stale` — 推一下代码，刚才认证失败了（ask → overwrite → retry）
- `2026-01-01-secret-hygiene` — 令牌只进 secrets，对话写占位符
