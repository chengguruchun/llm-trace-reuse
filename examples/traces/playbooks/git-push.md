# git push

Same request (推一下 / git push / 推到远端) — skip planning.

1. Commit only if the user asked to ship uncommitted work.
2. `git push` the current branch to the remote they named (default `origin`).
3. Auth order:
   - Local file exists → use it via a throwaway `GIT_ASKPASS` (do not put the token in the remote URL).
   - Missing file or `Access denied` → **stop and ask for a token**.
   - User gives a token → overwrite `.pathbook/secrets/git.pat`, then push again.
4. Token stays in that gitignored file. Never in the episode body.

Avoid: retrying the keychain in a loop; guessing a token from an old conversation.
