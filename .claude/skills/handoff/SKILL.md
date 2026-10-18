---
name: handoff
description: Log the work in prep/local_context.md, commit, push the current branch, and open or update a pull request to main. Use when the user says handoff, checkpoint and push, open a PR, or ship to the branch.
disable-model-invocation: true
---

# Handoff: log, commit, push, PR

Stop at the first failure and report it. Never force-push, never rebase, never merge into main yourself.

1. **Branch.** `git branch --show-current`. If it is `main`, stop: work must go through a PR.
2. **Log first.** Update `prep/local_context.md` (gitignored, never committed). Append a log entry for the work since the last entry, using the template in that file: Done (paths, what changed), Mistakes / fixes, Direction (where this leaves us against the plan, and what comes next). Then rewrite its "Current state" and "Next steps" so they are true after this push. Facts only: don't record a check as passing unless it ran in this session. Never write DSNs, keys or tokens.
3. **Review the changes.** `git status --porcelain` and `git diff`. Refuse to stage, and tell the user about, anything matching `.env*`, `*.key`, `data/**` outside `data/samples/`, `prep/**`, or a file containing what looks like a DSN or API key. List any changed path outside the folders the user's track owns (see `CLAUDE.md`), plus the shared ones (`contracts/`, `.claude/`, `tools/status/`, `CLAUDE.md`, `README.md`, `.gitignore`), and ask before staging those. Contract changes need all four owners to agree.
4. **Check.** If `contracts/` or any `data/samples/` file changed, run `python contracts/validate.py` (and the validator on the changed samples) with the project venv. Run the owner's tests if they exist. Stop on failure.
5. **Commit.** Stage only the reviewed paths by name (no `git add -A`). Write a commit message: one summary line, then a short body explaining what and why. Code files contain no comments, so the explanation belongs here. End with the attribution line the session's instructions specify.
6. **Push.** `git push -u origin <branch>`. If SSH fails because the key needs a passphrase in a non-interactive shell, stop and ask the user to run the push themselves (`! git push -u origin <branch>`).
7. **Pull request.** Requires `gh` logged in (`gh auth status`); if it isn't, ask the user to run `! gh auth login` once and stop.
   - If a PR from this branch to `main` is already open (`gh pr list --head <branch> --base main --state open`), don't open another; the push already updated it. Edit its description (`gh pr edit`) if the summary changed.
   - Otherwise `gh pr create --base main --head <branch>` with a title naming the milestone and a body containing: what the branch adds (bullets by folder), how to run and check it (exact commands and expected output), anything that needs the team's OK (shared paths), and open questions. End the body with the attribution line the session's instructions specify.
8. **Report.** The commit hash, the PR URL, and the new "Next steps" from the log.
