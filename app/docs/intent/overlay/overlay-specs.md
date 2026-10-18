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

- [ ] **OVERLAY-020**: When a `round_end` event for the live set arrives on the state stream, the overlay shall show the between-round card for that event's round, centered horizontally, 1000 px wide, with its bottom 64 px above the bottom edge.
- [ ] **OVERLAY-028**: The overlay shall not show the between-round card on the arrival of a `coach` record or a `round_summary` record.
- [ ] **OVERLAY-021**: When a `round_start` event for the card's set arrives on the state stream while the between-round card is showing, the overlay shall hide the card, whatever the event's round.
- [ ] **OVERLAY-025**: When a `state` record for the card's set arrives with a round later than the between-round card's round, the overlay shall hide the card.
- [ ] **OVERLAY-026**: When a `state` record for a set other than the between-round card's arrives, the overlay shall hide the card.
- [ ] **OVERLAY-027**: When the round stops being live while the between-round card is showing, the overlay shall hide the card.
- [ ] **OVERLAY-022**: The between-round card for round n shall show "Round <n> goes to you", "Round <n> goes to <bot character>" or "Round <n> is a draw" from the latest round summary for the card's set and round n, or "Round <n>" while no such summary has arrived.
- [ ] **OVERLAY-023**: The between-round card for round n shall show the `text` of the latest `coach` record for the card's set and round n at 30 px bold on the mat ground.
- [ ] **OVERLAY-029**: While no `coach` record for the card's set and round has arrived, the between-round card shall show "Coach is reviewing the round…" at 30 px in `--color-text-muted` in place of the coach text.
- [ ] **OVERLAY-024**: While the card's `round_end` event does not carry `detail.match_over: true`, the between-round card for round n shall show, in the display face in `--color-primary`, the whole seconds left of a 10-second countdown that starts when the `round_end` event reaches the overlay and holds at 0, over "Round <n + 1>", and a bottom bar whose `--color-primary` fill is proportional to the time left.
- [ ] **OVERLAY-030**: While the card's `round_end` event carries `detail.match_over: true`, the between-round card shall show "Set over" at 28 px (`--text-xl`) in the display face in `--color-primary` in place of the seconds and the round label.
- [ ] **OVERLAY-031**: While the card's `round_end` event carries `detail.match_over: true`, the between-round card shall not draw the bottom bar.

## Implemented in

| Spec IDs | Entry point |
|---|---|
| OVERLAY-001 – OVERLAY-031 | `src/renderer/src/overlay.tsx` (`OverlayContent`, `Habits`, `BetweenRounds`) |
