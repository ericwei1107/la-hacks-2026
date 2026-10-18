# Punish rate: unavailable wording review

Scope: Stats headline only. The analytics contract already permits a null rate.
A null punish rate can mean no opportunities or insufficient recovery evidence.

## High-level design check

The app remains a view over analytics. Existing G8 (designed empty/offline states)
and “arithmetic in the app, judgment in the services” cover this change. No HLD or
contract field change is needed.

## Detailed design proposal

In `app/docs/intent/main-window/stats/stats-design.md`, replace the null-rate
state with:

- A null punish rate reads as an em dash with “Not enough data this set”.
- Other null rates read as an em dash with “Didn't come up this set”.

Rationale: the existing response does not distinguish absent opportunities from
unknown timing. Neutral wording covers both without making a gameplay claim.

## Specification proposal

Update MAIN-STATS-008 in `stats-specs.md`:

“When punish rate is null, the Stats screen shall show an em dash with ‘Not
enough data this set’; when another rate is null, it shall show an em dash with
‘Didn't come up this set’.”

Keep the specification unchecked until the required inspection is complete.

## Exact implementation proposal

In `app/src/renderer/src/main-window/screens/Stats.tsx`, change only the null
punish-rate note from `"Didn't come up this set"` to `"Not enough data this set"`.

## Edge audit and validation

- null: em dash and neutral note; no comparison with last set.
- 0: 0%, not unavailable; existing comparison behavior retained.
- .2: 20%, existing comparison behavior retained.
- Previous set unavailable: no fabricated delta.
- Low and throw rates: unchanged.

Run app typecheck and build, then inspect spec against code. No automated app
tests are added, per the app's owner instructions.

## Required workflow exception

`app/AGENTS.md` says: “Consult the linked-intent-dev skill for ALL code changes in
app/” and “Each phase's output is inspected — by the user or an inspector they
name — before the next begins.” The skill was not found in the project or the
installed skill roots. No app source has been changed. The user can explicitly
approve this complete, bounded proposal as an exception to the missing-skill and
sequential-inspection requirements, or leave it for Chloe's workflow.

## Completion

The user explicitly approved the bounded workflow exception on October 18, 2026.
The design, MAIN-STATS-008 and the exact null-note implementation were updated in
the isolated worktree. Spec-to-code inspection, app typecheck and production build
pass. No native UI observation is claimed.
