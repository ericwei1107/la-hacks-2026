---
name: team-status
description: Report where each of Kumite's four tracks stands and what to do to integrate them. Use when anyone asks for team status, progress, who is blocked, what is ready to merge, or how integration is going.
---

# Team status

Kumite is built by four people on separate branches who meet only at `contracts/`. This skill tells the asker, in under a minute of reading, where every track is and what has to happen next for the pieces to fit.

## 1. Gather facts

Run, from the repo root:

```
python3 tools/status/status.py
```

It fetches every branch, then reports for each branch: commits since main, which track folders it touches, rule violations, pairwise merge conflicts, per-track milestone signals, `GET /health` on the three services, and contract validation of every `data/samples/*.jsonl` on every branch. If the fetch fails, say so: the report then reflects the last fetched state, not live state.

Use `--json` if you need to compute something from the output. Use `--no-fetch` only if the asker says the network is down.

## 2. Read beyond the script

The script's milestone signals are coarse (`unknown` means there is no file signal for that milestone, not that it is undone). For each track, read the branch's recent commit subjects and skim the diff of its own folders (`git diff origin/main...origin/<branch> -- <folders> --stat`, then the files that matter) to judge which milestone it has actually reached. Compare against the hour in the day: the event started the morning of October 17, 2026; ask the asker for the current hackathon hour if you can't infer it.

Check integration seams specifically:
- Does each service implement the routes in `contracts/api.md` with the shapes in `contracts/*.schema.json`? Grep the route strings on each branch.
- Does each client (the app, the brain calling `/coach/round`, the coach agent calling analytics) point at the address variables `KUMITE_BRAIN_URL`, `KUMITE_REPLAY_URL`, `KUMITE_ANALYTICS_URL` rather than hard-coded hosts?
- Is there a real recording in `data/samples/` yet (M1), and do the other tracks' services read it without errors?
- Do the mock servers in `tools/mock/` still match the contracts?

## 3. Standing checks

`tools/status/checks.json` lists per-person items that stay on the report until done, each with the hour window it is due (`due`). The script marks each one `on_main`, `on_branch (<branch>)`, `pending` (not found in code anywhere), or `manual` (no code signal; judge it yourself). Report every `pending` item whose window has started or passed under its owner, and every `on_branch` item as "done but not merged". Mention items not yet due only if the asker wants the full list. To add a new standing item for anyone, add it to `checks.json`.

If the Sentry MCP tools are available (org `university-of-maryland-ma`, projects `kumite-analytics`, `kumite-brain`, `kumite-replay`, `kumite-app`), also check live Sentry state and attribute it to the project's owner:
- Which projects have received any event in the last 24 hours. A project whose `sentry-init` check is done but which has no events means the DSN is missing or wrong in that service's environment.
- New unresolved issues in the last few hours per project: title and link, under the owner's name.
- From hour 14 onward, the `environment` tag on recent events. Events from the demo laptop tagged `development` mean `SENTRY_ENVIRONMENT=demo` was not set there; tell Sahil.
- For `kumite-app`, whether recent stack frames are minified (one-letter function names, bundled paths). If so, source maps are not uploaded; tell Chloe to run the `sentry-fix-stack-traces` skill.

Never print DSNs or keys in the report.

### Requests between teammates

An entry with a `from` field is a request one teammate made of another. Its `doc` points to the instructions under `tools/status/requests/`. When the person running this skill is the recipient (match `git config user.name`/`user.email` against `aliases` in `milestones.json`), lead their block with these requests and offer to start on them. When they are the sender, report which of their requests are still open. `python3 tools/status/status.py --inbox` prints just the current person's view; a SessionStart hook in `.claude/settings.json` runs it at the start of every session.

To make a request for someone, when asked: add an entry to that person's track in `checks.json` with `from`, `due`, `todo`, a `doc` file in `tools/status/requests/` holding the full instructions (no DSNs, keys or tokens, since the repo is public), and, when possible, a `grep` and `paths` that prove it's done so it closes itself. Then commit and push it (the `/handoff` skill does this). The tracker uses the most recently committed `checks.json` across all branches, so a request is visible to everyone as soon as it's pushed, even before it's merged to main.

## 4. Report

Lead with what needs action. Keep it short enough to read aloud to the team.

1. **Blockers and violations.** Every BLOCK flag (contract edits, data outside `data/samples/`, secrets), every merge conflict between branches, and anyone waiting on someone else. Name the person and the fix.
2. **One block per person:** owner, milestone reached vs. where the plan says they should be at this hour, last push time, then their open standing checks and any Sentry findings as a short to-do list. Flag anyone who hasn't pushed in over two hours, since unpushed work is invisible to everyone else.
3. **Ready to integrate:** which branches can merge to main now without conflicts or failing validation, in the order to merge them.
4. **Next integration step:** the single most useful thing the team can do next to reduce friction.

Do not edit any track's code, merge branches, or push. This skill only reports; the owners act.
