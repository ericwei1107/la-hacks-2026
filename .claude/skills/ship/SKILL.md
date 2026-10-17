---
name: ship
description: Ship the current branch to main safely with a no-ff merge after checks and explicit confirmation. Never force-pushes.
disable-model-invocation: true
---

# Ship the current branch to main

Stop at the first failure and leave main untouched. Never force-push. Never rebase.

1. Record the current branch name (`git branch --show-current`). If it is `main`, stop.
2. Confirm the working tree is clean with `git status --porcelain`. If anything is listed, stop and report it.
3. Run the /sync steps: `git fetch origin`, `git merge origin/main`. If there are conflicts, report them and stop.
4. Run the game tests if they exist (`python -m pytest game` when a `game/tests` directory or `game/test_*.py` files exist). Then run `python contracts/validate.py`. If either fails, stop and report the output.
5. Run `git diff --name-only origin/main...HEAD`. If any path is outside `game/`, `data/samples/`, `.claude/skills/`, or is not exactly `.gitignore`, list those paths and stop.
6. Push the branch (`git push`) so origin has the merged state.
7. Show the user the file list from step 5 and a three-line summary of what the branch adds. Ask for an explicit yes. Do not continue without it.
8. After the yes:
   - `git switch main`
   - `git pull --ff-only`
   - `git merge --no-ff <branch> -m "<one-line milestone summary>"` with a body listing the milestone and key files
   - `git push`
   - `git switch <branch>`
9. If `git pull --ff-only` or the merge fails, run `git merge --abort` if a merge is in progress, switch back to the branch, and report. If `git push` of main is rejected, do not force and do not reset; report that local main holds an unpushed merge commit and ask the user how to proceed before touching it.
10. Report the merge commit hash on main and `git log --oneline -3 origin/main`.
