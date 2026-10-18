# Devil Jin vs Kazuya

What Devil Jin should expect from Kazuya, and what Devil Jin can punish. Generated from `characters/kazuya/moves.json` and `characters/devil_jin/punishers.json`.

## What to expect

- Pressure character built around the Wind God Step (wavedash) cancels and the Electric Wind God Fist (EWGF).
- The electric f,n,d,df+2 is +5 on block and launches on hit; the non-electric version is -10 on block and punishable. At low difficulty the bot should mostly produce the non-electric version, at high difficulty the electric one.
- Mixes mids against lows: the hellsweep f,n,d,DF+4 is -23 on block, so it should only be thrown when the opponent is expected to stand and block.
- Dislikes being stepped (design note); his homing moves are listed under tracking and homing moves below.

## Punishable on block

`Punish with` is Devil Jin's best standing punisher for that gap (the move's on-block value, clamped to i10 to i20). Against crouching or low moves use the crouching list in `punishers.json`.

| Move | Name | Level | Startup | On block | Punish with |
|---|---|---|---|---|---|
| `df+3+4,1` |  | mid | i11 | -11 | `2` |
| `b+1` |  | high | i11 | -10 | `2` |
| `f,n,d,df+2` | Wind God Fist | high | i11 | -10 | `2` |
| `d+4` | Crouch Shin Kick | low | i12 | -15 | `b+1+3` |
| `1+2` | Acute Pain | mid/mid | i12 | -13 | `df+1` |
| `1,1,2` | Flash Punch Combo | mid | i13 | -17 | `b+1+3` |
| `db+1` |  | mid | i13 | -10 | `2` |
| `df+2` | Abolishing Fist | mid | i14 | -12 | `b+1` |
| `df+4,4` | Tsunami Kick | mid | i15 | -15 | `b+1+3` |
| `ws4,4` | Tsunami Kick | mid | i15 | -15 | `b+1+3` |
| `b+3,1,4,1` | Demon's Wrath | mid | i15 | -14 | `df+1` |
| `uf+2` | Hook | high | i15 | -12 | `b+1` |
| `f,n,d,DF+4` | Spinning Demon | low | i16 | -23 | `b+1+3` |
| `ws2` | Demon God Fist | mid | i16 | -18 | `b+1+3` |
| `d+3` | Crouch Spin Kick | low | i16 | -17 | `b+1+3` |
| `df+1,4` | Slaughter High Kick | high | i16 | -11 | `2` |

## Lows to block crouching

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `d+1` | Crouch Jab | special_low | i10 | -5 |  |
| `d+2` | Crouch Straight | special_low | i11 | -4 |  |
| `d+4` | Crouch Shin Kick | low | i12 | -15 |  |
| `b+3,1,4` |  | low | i16 | -10c |  |
| `d+3` | Crouch Spin Kick | low | i16 | -17 |  |
| `f,n,d,DF+4` | Spinning Demon | low | i16 | -23 |  |
| `db+3` | Sliding Low Kick | low | i19 | -12 |  |
| `b+3,1,4,3` | Reign of Terror | low | i20 | -13c |  |

## Tracking or homing moves (sidestepping is unreliable)

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `1,2,2~3` | Twin Fang Shattered Spine | mid | i23 | -9 | left |
| `b+4` | Flash Tornado | high | i17 | -5 | homing |
| `df+2` | Abolishing Fist | mid | i14 | -12 | homing |
| `ws2` | Demon God Fist | mid | i16 | -18 | homing |
| `ws3` | Engetsusen | mid | i21 | -5 | homing |

## Moves that leave them plus on block (do not press buttons)

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `1` | Jab | high | i10 | +1 |  |
| `f+4` | Right Splits Kick | mid | i19 | +4c |  |

## Throws and the break that answers them

| Throw | Startup | Break |
|---|---|---|
| `1+3` | i12 | 1/2 |
| `2+4` | i12 | 1/2 |
| `Back throw` | i12 | not stated |
| `Left throw` | i12 | 1 |
| `Right throw` | i12 | 2 |
| `uf+1+2` | i12 | 1+2 |
