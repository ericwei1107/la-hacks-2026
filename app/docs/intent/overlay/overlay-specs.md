# Overlay specs

Design: `overlay-design.md`

## Layout and live set

- [ ] **OVERLAY-001**: The overlay page shall lay out its content in a 1920 × 1080 space with a transparent background everywhere outside the HUD and the between-round card.
- [ ] **OVERLAY-002**: The overlay shall treat the `session_id` of the latest `state` record on the brain's state stream as the live set.
- [ ] **OVERLAY-003**: The overlay shall consider a round live while the latest `state` record was received less than 2 seconds ago.

## HUD

- [ ] **OVERLAY-010**: While a round is live and the between-round card is not showing, the overlay shall show the HUD at (48, 136), 460 px wide (`--container-hud`), on `--color-overlay` at 90% with a 4 px `--color-overlay-line` rule along its top.
- [ ] **OVERLAY-011**: The HUD shall show the brain config's bot character in the display face and "Level <difficulty>".
- [ ] **OVERLAY-012**: When the state stream has delivered a `plan` record for the live set, the HUD shall show "Plan:" followed by the plan's `note`, setting notation tokens in mono.
- [ ] **OVERLAY-013**: While no `plan` record for the live set has arrived, the HUD shall not show a plan row.
- [ ] **OVERLAY-014**: The HUD shall show one row per habit of the live set's last learning round, with its belt in the night variant, its name, its rank name and its mastery as a whole percent.
- [ ] **OVERLAY-015**: When a `round_summary` for the live set arrives, the overlay shall refetch that set's learning metrics.
- [ ] **OVERLAY-016**: When a habit's situation appears in the `exploited` list of the latest round summary for the live set, its HUD row shall show a "Bot's target" tag on `--color-bot` and a 10% `--color-bot` background.
- [ ] **OVERLAY-017**: When a habit is fixed, its HUD row shall show a "Fixed" tag outlined in `--color-overlay-text`.
- [ ] **OVERLAY-018**: The HUD shall order habit rows with targeted habits first, then by mastery from lowest.
- [ ] **OVERLAY-019**: While the live set has no learning rounds, the HUD shall show "Learning your habits. Belts show up after round 1." in place of the habit rows.

## Between-round card

- [ ] **OVERLAY-020**: When a `coach` record for the live set arrives on the coach stream, the overlay shall show the between-round card centered horizontally, 1000 px wide, with its bottom 64 px above the bottom edge.
- [ ] **OVERLAY-021**: The overlay shall hide the between-round card 10 seconds after it appears, or earlier when a `state` record arrives for a round later than the coach record's round.
- [ ] **OVERLAY-022**: The between-round card shall show "Round <n> goes to you", "Round <n> goes to <bot character>" or "Round <n> is a draw" from the live set's round summary for round n, or "Round <n>" when there is none.
- [ ] **OVERLAY-023**: The between-round card shall show the coach record's `text` at 30 px bold on the mat ground.
- [ ] **OVERLAY-024**: The between-round card shall show the whole seconds left in the display face in `--color-primary` over "Round <n + 1>", and a bottom bar whose `--color-primary` fill is proportional to the time left.
