# Devil Jin vs Shaheen

What Devil Jin should expect from Shaheen, and what Devil Jin can punish. Generated from `characters/shaheen/moves.json` and `characters/devil_jin/punishers.json`.

## What to expect

- Simple, solid pokes with a snake stance (SNK) that extends strings; low effort to model.
- Jabs 1 and 2 are i10 and plus or even on block, df+2 is a launcher with homing, and the tracking list below covers sidesteppers.

## Punishable on block

`Punish with` is Devil Jin's best standing punisher for that gap (the move's on-block value, clamped to i10 to i20). Against crouching or low moves use the crouching list in `punishers.json`.

| Move | Name | Level | Startup | On block | Punish with |
|---|---|---|---|---|---|
| `d+3+4` | Crouch Shin Kick | low | i12 | -15 | `b+1+3` |
| `ws3` |  | mid | i13 | -11 | `2` |
| `4` | Hallux Kick | high | i13 | -10 | `2` |
| `db+2` |  | mid | i14 | -10 | `2` |
| `uf+4` | Altair | mid | i15 | -13 | `df+1` |
| `ws2` | Hawk Edge | mid | i16 | -17 | `b+1+3` |
| `d+3` | Silent Rigel | low | i16 | -14 | `df+1` |
| `b+4` | Broken Mirage | mid | i17 | -15 | `b+1+3` |
| `df+3` | Whirlwind Kick | mid | i17 | -13 | `df+1` |
| `ws3,3` | Double Scorpion | mid | i17 | -13 | `df+1` |
| `f,F+3` | Hunting Falcon Dive | mid | i17 | -12 | `b+1` |
| `db+3,4` | Snake's Bite > Rising Scimitar | high | i18 | -13 | `df+1` |
| `f+2,3` | Silent Sting | high | i18 | -12 | `b+1` |
| `d+4` | Vicious Stomp | low | i19 | -12 | `b+1` |
| `db+3` | Snake's Bite | low | i20 | -17 | `b+1+3` |
| `d+1` | Hermit Needle | low | i20 | -13 | `df+1` |

## Lows to block crouching

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `db+1` | Crouch Jab | special_low | i10 | -5 |  |
| `d+3+4` | Crouch Shin Kick | low | i12 | -15 |  |
| `d+3` | Silent Rigel | low | i16 | -14 |  |
| `d+4` | Vicious Stomp | low | i19 | -12 |  |
| `d+1` | Hermit Needle | low | i20 | -13 |  |
| `db+3` | Snake's Bite | low | i20 | -17 |  |
| `f+2,4` |  | low | i22 | -13 |  |

## Tracking or homing moves (sidestepping is unreliable)

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `df+1` |  | mid | i13 | -1 | right |
| `df+3` | Whirlwind Kick | mid | i17 | -13 | homing |
| `f+3` | Crescent Moon | mid | i20 | -5 | tracking |
| `f+4` | Piercing Talon | high | i15 | +0 | homing |

## Moves that leave them plus on block (do not press buttons)

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `1` |  | high | i10 | +1 |  |
| `D*,u+2` | Al-Ghul | high | i17 | +6 |  |
| `f,f,F+2` | Antares | mid | i17 | +5 |  |
| `b+3` | Heel Strike | mid | i19 | +1c |  |

## Throws and the break that answers them

| Throw | Startup | Break |
|---|---|---|
| `1+3` | i12 | 1/2 |
| `2+4` | i12 | 1/2 |
| `Back throw` | i12 | not stated |
| `Left throw` | i12 | 1 |
| `Right throw` | i12 | 2 |
| `uf+1+2` | i12 | 1+2 |
