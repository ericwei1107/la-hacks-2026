# Acceptance: focus card, evidence and moments (Track D C5–C7)

Checked on 2026-10-18 on branch `chloe` at `561bcb0` plus the working changes, against Eric's insights branch `track-d-insights-v1` (`95b65a6`, with Garrett's approved action wording). `npm run typecheck` and `npm run build` pass.

## Fixture states

The built app ran with `KUMITE_INSIGHTS=1`, brain = mock brain serving `data/samples/live_learning`, and analytics = a local test server returning one of Eric's eleven public fixtures for `/insights` (session id rewritten to the selected set) and passing every other route to real analytics on the same sample. Screenshots at 1920 × 1080 are in `2026-10-18-focus-card/`.

| Fixture | Card shows | Screenshot |
|---|---|---|
| real | Low defense focus, "0 of 16 lows blocked" 0%, reason, the approved action "Review these lows and practice recognizing low/mid choices; avoid crouching continuously."; throw defense early signal "4 throws seen; more needed…" 25%; "Estimated punish conversion" 0 of 6; evidence "Not blocked" rows; "Showing 3 of 54" "Took damage" moments (`limit=3`) | `real.png` |
| observed | Synthetic tag; low defense focus 0 of 6 | `observed.png` |
| early_signal | "More observations needed"; "3 lows seen; more needed for an automatic focus" | `early_signal.png` |
| no_opportunities | "More observations needed"; every metric "No opportunities observed" with "—"; "No moments recorded yet." | `no_opportunities.png` |
| invalid_recording | "This set's data needs review before it can suggest a focus."; every metric "Data needs review", no rates | `invalid_recording.png` |
| orphan_break | Throw defense alone "Data needs review"; the others "No opportunities observed" | `orphan_break.png` |
| manual_focus | "Selected focus" tag; throw defense 0 of 3 | `manual_focus.png` |
| pending_learning → current_learning | "Round 2 learning is still being saved." with the counts kept, then the note gone on the current snapshot | `pending_learning.png`, `current_learning.png` |
| mixed_outcomes | Selected moment lists "Blocked" and "Not punished", detail in place (event, by the bot, against you, −12, no response) | `mixed-moment-selected.png` |
| synthetic | Synthetic tag; 8 of 15 lows blocked 53% | `synthetic.png` |
| real, then 503 | Last good view kept, "Through completed round 4 · Not up to date" | `real-stale-503.png` |

No null value rendered as 0%. The action text shows because `action_reviewed` is now true; with it false the card shows "Review these moments" (checked on the earlier fixtures).

## Selection and keyboard

- Enter on a focused evidence row expanded it (`aria-expanded` true); Space collapsed it; the focus ring showed.
- An expanded row stayed open across a refetch with the same lines and across a 503 (stale view); it closed when the reply's lines changed.
- Each row's outcome is a word with a mark (✓, ✕, or a dot for damage), never color alone.

## Live refresh scenario

Eric's two-process scenario from `tools/mock/README.md` on his branch, brain at `--rate 240` (about 10 s per round), `--learning-delay 3`, real analytics with `KUMITE_EXPERIMENTAL_INSIGHTS=1` reading the live folder. A watcher read the card every 0.5 s.

| Run | Observed |
|---|---|
| Normal | No completed rounds → round 1 with "Round 1 learning is still being saved." → note cleared about 2 s later → round 2, early signal 3 lows → round 4, "0 of 16 lows blocked" |
| `--duplicate-summaries` | Same end state, through round 4 at 0 of 16: duplicates not double-counted |
| `--drop-after-summary` | Same end state: the sockets reconnected and the card converged |

In all three runs analytics answered `/insights` slowly or not at all from about 20 s to 45 s (rounds 2–3 at 4× speed), so the card skipped from round 2 to round 4. That is a backend timing issue to report, not a card behavior; the card kept its last view throughout.

## Not exercised here

- Two live sets at once, to show no set takes another's numbers. The card drops any reply whose `session_id` is not the selected set (MAIN-FOCUS-003), read in code.
- The early-signal threshold number: the reply has no threshold field yet, so the line reads "more needed".
- Real host run with Sahil's brain and analytics.
