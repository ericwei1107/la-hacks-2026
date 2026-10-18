> Current follow-up: [version-6 local implementation and rollout status](punish-rollout.md). The audit below records Garrett’s original review.


# Estimated punish conversion: audit of the real M3 session

Audited October 18, 2026 by Track D; reviewed by Garrett the same day (his answers and one correction are below). Session `2026-10-18T05-14-03_sahil_djin_vs_kaz` (`data/samples/live_learning`), human Devil Jin (slot 0), bot Kazuya. Calculation version 4 reports **0/6**. Nothing in the metric was changed by this audit; punishment focus stays disabled.

## Method

For each of the six opportunities the current rule selects (a bot move blocked by the human at actor-relative frame advantage ≤ −10), compare against:

- Garrett's `characters/kazuya/moves.json` on-block value for the bot's move id;
- the recorded state frames: the first frame each player is actionable again (`frames_until_actionable` returns to 0 after blockstun or recovery), the human's first new move (`frame_in_move == 1`), and any bot follow-up before its recovery;
- the first human hit on the bot, and Garrett's `characters/devil_jin/punishers.json` tiers for that disadvantage.

Measured advantage is the bot's recovery frame minus the human's. A hit is a real punish when it lands at or before the bot's recovery frame.

## Results

| # | Round, frame, line | Bot move (catalog on block) | Recorded / measured adv | Human free → bot free | What the human did | Current rule | Audit verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | R1 f864, line 698 | f,n,d,df+2 Wind God Fist (−10) | −10 / 10 | 883 → 893 | Pressed 2 (i10) 2 frames after recovering; hit at 896 for 9, 3 frames after the bot recovered | Miss | **Miss, correctly** (late input; −10 allows only an instant i10 such as 2 or 1) |
| 2 | R1 f1492, line 1361 | df+2 Abolishing Fist (−12) | −12 / 12 | 1511 → 1523 | Pressed 1 two frames after recovering; 1,2 hit at 1522 for 5, one frame before the bot recovered | Miss | **Punish landed: false negative** |
| 3 | R2 f544, line 2866 | df+2 Abolishing Fist (−12) | −12 / 12 | 563 → 575 | Started db+2 Malicious Mace (i21) at 569; hit at 590, after the bot recovered at 575 | Miss | **Miss, correctly** (late attack: an i21 move cannot punish −12) |
| 4 | R2 f1041, line 3397 | 1+2 Acute Pain (−13) | −13 / 13 | 1060 → 1073 | Only unmapped moves with no attack buttons (1443, 1468) start before recovery; first attack input at 1103 | Miss | **Miss, correctly** (no punishing attack) |
| 5 | R2 f1771, line 4175 | df+2 Abolishing Fist (−12) | −12 / 12 | 1791 → 1803 | Pressed heat on the first free frame (heat activation, not an attack); no hit | Miss | **Miss, correctly**: "Heat activated; no punishing attack landed before recovery" |
| 6 | R3 f1470, line 6589 | move 1717, not in catalog | −25 / not a gap | 1504 → 1512 | Bot continued the string (move 1720 blocked at 1486); after it the bot is only 8 frames behind | Miss | **Not an opportunity: false positive** (mid-string block) |

Per the audit: **1 punish landed out of 5 real opportunities**, against the reported 0/6.

## Findings

1. **The producer's frame advantage is accurate.** For all five catalogued moves the recorded value matches Garrett's on-block value and the measured recovery gap exactly.
2. **The window is anchored at the wrong frame.** The rule accepts a hit within `|advantage| + 10` frames of the *block event*. The human first spends 19–20 frames in blockstun (34 in case 6), so even an instant 10-frame punisher lands about 29–32 frames after the block. For any move between −10 and −18 the rule can essentially never count a real punish. Case 2 is a real punish it rejected. The checked-in synthetic session reports 9/9 only because its generator places hits inside this window.
3. **String continuations create false opportunities.** Case 6 is the first hit of a string the bot continued 16 frames later, so its −25 is not a punish window. The producer's `string_continued: false` is set at read time, before the follow-up appears.
4. **The failure reasons are actionable.** Two misses were late attacks (case 1: the right i10 jab, about 2 frames late; case 3: an i21 move that is too slow for −12), one had no punishing attack (case 4), and one was heat activation instead of an attack (case 5). That is coaching material if the metric becomes trustworthy.
5. **Correction to the first draft of this audit.** It detected inputs only from `buttons_pressed` and called case 3 "no attempt". Garrett found the attack: the press appears only in `buttons_held`. All six cases were rechecked by new-move starts (`frame_in_move == 1`); only case 3 changed.

## Proposed corrected rule (not implemented)

- **Opportunity:** a bot move blocked by the human at advantage ≤ −10, excluding cases where the bot starts another attack before its own recovery frame (a string continuation).
- **Recovery frames:** human free = first actionable frame after the blockstun from the event's `read_frame`; bot free = human free + |advantage|. Alternatively use the bot's own `frames_until_actionable`, which gave identical results here.
- **Converted:** a human hit on the bot lands at or before bot free.

On this session that gives 1/5. Changing it alters `/stats` `punish_rate` and stored aggregates, so it needs calculation version 5, a scoped Tiger Data backfill with a zero-import repeat, regenerated examples, and owner sign-off. Until then keep punishment out of focus and labelled "estimated".

## Garrett's review (October 18)

Garrett re-checked the recording. His full write-up (`replay/PUNISH_FOCUS_REVIEW.md`) is on his machine and not yet pushed.

1. **Case 2 counts as a landed punish.** The jab lands at frame 1522 while Kazuya still has one recovery frame remaining.
2. **Case 5 wording:** "Heat activated; no punishing attack landed before recovery." Do not label it "no input".
3. **Case 6:** moves 1717 and 1720 are both unmapped, so a named natural string cannot be confirmed. The recorded continuation still invalidates that opportunity.
4. **No extra tolerance.** Test the exact recovery-frame boundary; ambiguous timing stays uncertain rather than counted.
5. **Corrected punish focus is conditionally acceptable.** Keep it disabled until the corrected reducer, its regressions, a calculation-version bump and the backfill are verified.
6. **Correction:** case 3 was a late attack, not "no attempt" (attack starts at 569, hits at 590, after recovery at 575). Applied above.

He approved the low-defense and throw-defense action wording. The generic punish wording is acceptable, but that does not approve the current metric. `focus.py` keeps `punish_validated=False`.

## Reproduce

The audit script lives outside the repo (Track D scratch). The frames above can be checked directly in the recording at the listed lines: each block event's `detail.read_frame`, then each player's `frames_until_actionable` and `buttons_pressed` in the following state records.
