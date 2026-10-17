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

## 3. Report

Lead with what needs action. Keep it short enough to read aloud to the team.

1. **Blockers and violations.** Every BLOCK flag (contract edits, data outside `data/samples/`, secrets), every merge conflict between branches, and anyone waiting on someone else. Name the person and the fix.
2. **One line per track:** owner, milestone reached vs. where the plan says they should be at this hour, last push time. Flag anyone who hasn't pushed in over two hours, since unpushed work is invisible to everyone else.
3. **Ready to integrate:** which branches can merge to main now without conflicts or failing validation, in the order to merge them.
4. **Next integration step:** the single most useful thing the team can do next to reduce friction.

Do not edit any track's code, merge branches, or push. This skill only reports; the owners act.
