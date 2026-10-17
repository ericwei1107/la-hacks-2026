# Devil Jin game plan

Style notes the plan thread reads. Facts below are generated from `moves.json`, `throws.json` and `options.json`.

## Style

- All-rounder with the same wavedash and EWGF toolkit as Kazuya, plus mid-launching strings out of the Mourning Crow stance (MCR) and mix-ups from while-standing moves.
- The electric f,n,d,df+2 is +5 on block and launches; the non-electric one is -10 and punishable.
- Used mainly as the human's character in testing; this file exists so the coach can validate moves and explain what Devil Jin could have done.

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
| `b+1+2` | Aratama Strike | mid | i20 | +3c |  |

## Risky moves (punishable on block, i10 or worse)

The bot should throw these only when it expects the opponent to be hit or to guess wrong.

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `1,2,4` | One Two Knee | mid | i11 | -10 |  |
| `f,n,d,df+2` | Wind God Fist | high | i11 | -10 |  |
| `d+4` | Crouch Shin Kick | low | i12 | -15 |  |
| `1,1,2` | Flash Claw Combo | mid | i13 | -17 |  |
| `df+4,4` | Tsunami Kick | mid | i13 | -15 |  |
| `b+2` |  | high | i14 | -13 |  |
| `ws2` | Alaya | mid | i14 | -12~-11 |  |
| `ws3` | Organ Wrecker | mid | i14 | -11 |  |
| `b,f+2,1` |  | mid | i14 | -10 |  |
| `d+3+4` | Double Lift Kicks | mid/mid | i15 | -15 |  |
| `f+4` |  | mid | i15 | -12 |  |
| `f+2,4` | 893P > Knee Kick | mid | i15 | -11 |  |

## Tracking and homing moves

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `1+2` | Tsujikaze | mid/mid | i17 | -12 | homing |
| `3,1,2` | Hell Cyclone | mid | i25 | -11 | right |
| `3,1,4` | Hell Spiral | mid | i23 | -9 | right |
| `4` | Last Rites | high | i17 | -5 | homing |
| `b+1` |  | high | i12 | -6 | right |
| `b+1,2` | Brimstone Strike | mid | i23 | -14 | right+left |
| `b,f+2,1,2` | Laser Cannon | mid | i22 | -8 | right+left |
| `b,f+2,1,df+2` | Laser Scraper | mid | i18 | -13 | right |
| `d+3` | Broken Plate | low | i18 | -12 | homing |
| `df+2` | Bloody Glaive | mid | i15 | -9 | tracking |

## Throws and their break inputs

| Throw | Name | Startup | Break |
|---|---|---|---|
| `1+3` | Double High Sweep | i12 | 1/2 |
| `2+4` | Judgment | i12 | 1/2 |
| `df+2+3` | White Mountain | i12 | 2 |
| `f,hcf+1+2` | Obliteration | i12 | 1+2 |
| `qcb+1+3` | Complicated Wire | i12 | 1 |
| `uf+1+2` | Stonehead | i12 | 1+2 |
