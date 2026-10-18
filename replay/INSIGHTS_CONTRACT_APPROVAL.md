# Track C approval of additive insights contract registration

Garrett's Track C review, October 18, 2026.

**Yes to the three proposed additive contract changes**, as described in
`analytics/handoffs/insights-contract-draft.md` on `track-d-insights-v1`:

1. Add `contracts/insights.schema.json` from the reviewed public v1 schema,
   changing its title/description for registration and including the approved
   `focus.min_opportunities` addition described below.
2. Add the matching `contracts/examples/insights.json`, regenerated from the
   current verified builder. Do not retain the known incorrect v4 punish
   numbers as a frozen expected example.
3. Add the documented GET `/insights/{session_id}` row to `contracts/api.md`,
   with optional `limit=1..50`, default 5, and the stated 404/422/503 behavior.

**Yes to `focus.min_opportunities`: required integer, minimum 1, currently 5.**
It declares the observation threshold for automatic focus selection, allowing
the app to render an early-signal message without duplicating a backend rule.
It is not a confidence score or an assertion that five observations prove a
weakness. Manual focus can still select an early signal under the existing
policy. No existing field is renamed, removed or retyped.

Eric identified the not-yet-pushed implementation as `55a50e4`; approval is of
the exact described field/semantics, not a claim that commit was inspected.
An in-memory copy of the pushed schema plus that field validated all eleven
existing public fixtures after supplying threshold 5. Missing values, zero,
negative values, booleans, fractional values and null were rejected; 1 was
accepted. No contract or analytics files were edited for this check.

Retain the existing conditions: additive route on analytics :8767; brain-file
inputs only; no replay-report dependency; opt-in until all four owners agree;
source references, missing-data states and explicit estimated punish labels
remain intact. This is Track C approval only, not approval for another owner.
Generic punish wording approval is separate from mechanical/calculation
sign-off, and does not authorize enabling punishment focus.

At review time `95b65a6` records route approval on PR #25. Eric's separately
pushed `fix/punish-v6-rollout` at `bac884f` reports a corrected 1/5 estimate,
regenerated fixtures and scoped backfill evidence. That is new verification
material, not automatic Track C sign-off of the implementation or rollout.
The user relayed Sahil's and Chloe's yes on contract additions; Eric retains
the four-owner approval record and performs the contract registration/rollout.

No file under contracts/, analytics/, tools/, app/ or characters/ was modified
by this approval. Nothing was posted to GitHub or sent to a teammate by it.
