# King game plan

Style notes the plan thread reads. Facts below are generated from `moves.json`, `throws.json` and `options.json`.

## Style

- Throw-based grappler: command throws, chain grabs and mid pokes carry the offence.
- Command throws have different break inputs (qcf+1 breaks with 1, df+2+3 with 2, db+2+3 with 1+2 per field observation), so a player who always breaks the same way can be thrown with the other ones. This is the cleanest demonstration of the throw-break habit.
- Fast jabs (1 and 2 are i10) and the plus-on-block jabs let King keep the turn, then mix throws with mid pokes.

## Default option by situation

| Situation | Default | Other options |
|---|---|---|
| `plus_close` | `frame_trap` | `throw`, `low`, `mid_launcher`, `plus_pressure` |
| `even_close` | `poke` | `throw`, `low`, `mid`, `block` |
| `minus_close` | `block` | `safe`, `backdash`, `sidestep_left`, `sidestep_right`, `poke` |
| `minus_big` | `block` | `backdash`, `sidestep_left`, `sidestep_right` |
| `neutral_mid` | `poke` | `mid`, `tracking`, `low`, `wait`, `sidestep_left`, `sidestep_right`, `backdash` |
| `neutral_far` | `wait` | `approach`, `mid`, `mid_launcher` |
| `opp_whiff` | `whiff_punish` | `mid_launcher`, `poke` |
| `opp_knockdown` | `mid` | `low`, `throw`, `wait` |
| `opp_wall` | `mid_launcher` | `plus_pressure`, `throw`, `mid` |

## Prediction to option

| Opponent prediction | Options, in order |
|---|---|
| `opp_presses` | `frame_trap`, `block`, `backdash` |
| `opp_ducks` | `mid_launcher`, `mid` |
| `opp_steps` | `tracking` |
| `opp_passive` | `low`, `throw` |

## Moves that keep the turn (plus on block)

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `1` | Jab | high | i10 | +1 |  |
| `2` | Right Jab | high | i10 | +1 |  |
| `f+1+4` | Body Check | mid | i17 | +3 |  |
| `b+4` | Disgraceful Kick | high | i17 | +2 |  |
| `f,f,F+3` | Strong Knee | mid | i20 | +3 |  |

## Risky moves (punishable on block, i10 or worse)

The bot should throw these only when it expects the opponent to be hit or to guess wrong.

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `b+1+3` | Arm Whip | r(m) | i10 | None |  |
| `b+2+4` | Spinning Heel Hold | r(m) | i10 | None |  |
| `b+2+4:3+4` | Leg Screw > Figure Four Leg Lock | r(m) | i10 | None |  |
| `d+4` |  | low | i14 | -15 |  |
| `df+4` |  | low | i14 | -14 |  |
| `f,F+4` | Konvict Kick | mid/(t) | i15 | -15 |  |
| `ub+4` |  | mid | i15 | -13 |  |
| `uf+4` | Jumping Knee Lift | mid | i15 | -13 |  |
| `ws2,2` | Round Trip Chop | mid | i15 | -12 |  |
| `d+1,2` | Jab > Uppercut | mid | i15 | -11 |  |
| `f+2` |  | mid | i15 | -11 |  |
| `d+3+4` |  | low | i16 | -25 |  |

## Tracking and homing moves

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `db+3` | Crouching Low Kick | low | i23 | -14 | left |
| `df+3` |  | mid | i14 | -9 | right |
| `f+4` | Rolling Sobat | mid | i18 | -9 | homing |
| `f,F+1` | Jaguar Hook | mid | i20 | -5 | homing |
| `uf+1` | Water Parting Chop | high | i20 | -3 | homing |
| `ws2` |  | mid | i14 | -9 | homing |

## Throws and their break inputs

| Throw | Name | Startup | Break |
|---|---|---|---|
| `1+3` | Winding Nut | i12 | 2 |
| `2+4` | Suplex | i12 | not stated |
| `b+1+2` | Throw Away | i12 | not stated |
| `d+1+3` | Iron Lariat | i12 | not stated |
| `d+1+4` | Freedom Face Buster | i12 | not stated |
| `d+2+4` | V Driver | i12 | not stated |
| `db+2+3` | Figure Four Leg Lock | i12 | 1+2 |
| `db,n,f+2+4` | Tombstone Pile Driver | i11 | not stated |
| `df+1+3` | Reverse Arm Slam (RAS1) | i32 | not stated |
| `df+2+3` | Knee Bash | i12 | 2 |
| `df+2+4` | Reverse Special Stretch Bomb (RSSB1) | i32 | not stated |
| `f,f,F+2+4` | Tomahawk | i10 | not stated |
| `f,hcf+1` | Giant Swing | i10 | not stated |
| `f,hcf+2` | Tijuana Twister | i12 | not stated |
| `qcb+1+2` | Muscle Buster | i11 | not stated |
| `qcb+1+3` | Elevating Spine Cracker | i14 | not stated |
| `qcf+1` | Pile Driver (PD) | i11 | 1 |
| `uf+1+2` | Executioner Drop | i12 | not stated |
