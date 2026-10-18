# Shaheen game plan

Style notes the plan thread reads. Facts below are generated from `moves.json`, `throws.json` and `options.json`.

## Style

- Simple, solid pokes with a snake stance (SNK) that extends strings; low effort to model.
- Jabs 1 and 2 are i10 and plus or even on block, df+2 is a launcher with homing, and the tracking list below covers sidesteppers.

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
| `1` |  | high | i10 | +1 |  |
| `D*,u+2` | Al-Ghul | high | i17 | +6 |  |
| `f,f,F+2` | Antares | mid | i17 | +5 |  |
| `b+3` | Heel Strike | mid | i19 | +1c |  |

## Risky moves (punishable on block, i10 or worse)

The bot should throw these only when it expects the opponent to be hit or to guess wrong.

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `d+3+4` | Crouch Shin Kick | low | i12 | -15 |  |
| `ws3` |  | mid | i13 | -11 |  |
| `4` | Hallux Kick | high | i13 | -10 |  |
| `db+2` |  | mid | i14 | -10 |  |
| `uf+4` | Altair | mid | i15 | -13 |  |
| `ws2` | Hawk Edge | mid | i16 | -17 |  |
| `d+3` | Silent Rigel | low | i16 | -14 |  |
| `b+4` | Broken Mirage | mid | i17 | -15 |  |
| `df+3` | Whirlwind Kick | mid | i17 | -13 | homing |
| `ws3,3` | Double Scorpion | mid | i17 | -13 |  |
| `f,F+3` | Hunting Falcon Dive | mid | i17 | -12 |  |
| `db+3,4` | Snake's Bite > Rising Scimitar | high | i18 | -13 |  |

## Tracking and homing moves

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `df+1` |  | mid | i13 | -1 | right |
| `df+3` | Whirlwind Kick | mid | i17 | -13 | homing |
| `f+3` | Crescent Moon | mid | i20 | -5 | tracking |
| `f+4` | Piercing Talon | high | i15 | +0 | homing |

## Throws and their break inputs

| Throw | Name | Startup | Break |
|---|---|---|---|
| `1+3` | Desert Fang | i12 | 1/2 |
| `2+4` | Aldebaran | i12 | 1/2 |
| `Back throw` | Silent Death | i12 | not stated |
| `Left throw` | Chasm Drop | i12 | 1 |
| `Right throw` | Axel Spinner | i12 | 2 |
| `uf+1+2` | Wezen | i12 | 1+2 |
