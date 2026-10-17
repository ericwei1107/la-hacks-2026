# Kazuya game plan

Style notes the plan thread reads. Facts below are generated from `moves.json`, `throws.json` and `options.json`.

## Style

- Pressure character built around the Wind God Step (wavedash) cancels and the Electric Wind God Fist (EWGF).
- The electric f,n,d,df+2 is +5 on block and launches on hit; the non-electric version is -10 on block and punishable. At low difficulty the bot should mostly produce the non-electric version, at high difficulty the electric one.
- Mixes mids against lows: the hellsweep f,n,d,DF+4 is -23 on block, so it should only be thrown when the opponent is expected to stand and block.
- Dislikes being stepped (design note); his homing moves are listed under tracking and homing moves below.

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
| `f+4` | Right Splits Kick | mid | i19 | +4c |  |

## Risky moves (punishable on block, i10 or worse)

The bot should throw these only when it expects the opponent to be hit or to guess wrong.

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `df+3+4,1` |  | mid | i11 | -11 |  |
| `b+1` |  | high | i11 | -10 |  |
| `f,n,d,df+2` | Wind God Fist | high | i11 | -10 |  |
| `d+4` | Crouch Shin Kick | low | i12 | -15 |  |
| `1+2` | Acute Pain | mid/mid | i12 | -13 |  |
| `1,1,2` | Flash Punch Combo | mid | i13 | -17 |  |
| `db+1` |  | mid | i13 | -10 |  |
| `df+2` | Abolishing Fist | mid | i14 | -12 | homing |
| `df+4,4` | Tsunami Kick | mid | i15 | -15 |  |
| `ws4,4` | Tsunami Kick | mid | i15 | -15 |  |
| `b+3,1,4,1` | Demon's Wrath | mid | i15 | -14 |  |
| `uf+2` | Hook | high | i15 | -12 |  |

## Tracking and homing moves

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `1,2,2~3` | Twin Fang Shattered Spine | mid | i23 | -9 | left |
| `b+4` | Flash Tornado | high | i17 | -5 | homing |
| `df+2` | Abolishing Fist | mid | i14 | -12 | homing |
| `ws2` | Demon God Fist | mid | i16 | -18 | homing |
| `ws3` | Engetsusen | mid | i21 | -5 | homing |

## Throws and their break inputs

| Throw | Name | Startup | Break |
|---|---|---|---|
| `1+3` | Double High Sweep | i12 | 1/2 |
| `2+4` | Lightning Crash | i12 | 1/2 |
| `Back throw` | Reverse Neck Throw | i12 | not stated |
| `Left throw` | Steel Pedal Drop | i12 | 1 |
| `Right throw` | Skull Smash | i12 | 2 |
| `uf+1+2` | Stonehead | i12 | 1+2 |
