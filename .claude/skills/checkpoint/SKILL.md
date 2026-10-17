---
name: checkpoint
description: Print a checkpoint block for the planning chat and update the milestone table and notes in CLAUDE.local.md.
disable-model-invocation: true
---

# Checkpoint for the planning chat

1. Gather facts from this session and the repo: the current milestone, `git log --oneline` on the current branch since its last merge with origin/main, files added or changed under game/ and data/samples/, and the check the user ran with its actual output. Do not invent results; if a check was not run, say so.
2. Print one fenced block titled `Checkpoint for planning chat` containing, in this order:
   - Milestone and status (done, partial, blocked)
   - What was built: files with one line each
   - The exact check that was run and a summary of its output
   - Deviations from prep/design-doc.md or prep/verified-facts.md (or "none")
   - Open questions
   - Proposed next milestone and its first step
3. Update CLAUDE.local.md: set the Status column of the milestone row in the Milestones table, and replace or extend the Current notes with the verified facts from this milestone (short bullets, no speculation). Keep everything else in the file unchanged.
4. Show the user the diff of CLAUDE.local.md.
