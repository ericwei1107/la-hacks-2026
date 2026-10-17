---
name: sync
description: Fetch origin, merge origin/main into the current branch, and validate contracts. Stops on conflicts.
disable-model-invocation: true
---

# Sync with main

1. Run `git status --porcelain`. If the working tree has uncommitted changes, list them and ask whether to continue before merging.
2. Run `git fetch origin`.
3. Run `git merge origin/main` into the current branch. Never rebase, never force-push.
4. If the merge reports conflicts, run `git diff --name-only --diff-filter=U`, report every conflicted file, and stop. Do not resolve conflicts, do not run `git merge --abort`, and do not continue to the next step unless the user says so.
5. Run `python contracts/validate.py` and report PASS or FAIL with its output.
6. Report: the current branch, the commits merged in (`git log --oneline ORIG_HEAD..HEAD`, or "already up to date"), the validation result, and any files changed outside game/, data/samples/, .claude/skills/ and .gitignore that came in from main (for awareness only).
