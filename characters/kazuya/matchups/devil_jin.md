# Kazuya vs Devil Jin

What Kazuya should expect from Devil Jin, and what Kazuya can punish. Generated from `characters/devil_jin/moves.json` and `characters/kazuya/punishers.json`.

## What to expect

- All-rounder with the same wavedash and EWGF toolkit as Kazuya, plus mid-launching strings out of the Mourning Crow stance (MCR) and mix-ups from while-standing moves.
- The electric f,n,d,df+2 is +5 on block and launches; the non-electric one is -10 and punishable.

## Punishable on block

`Punish with` is Kazuya's best standing punisher for that gap (the move's on-block value, clamped to i10 to i20). Against crouching or low moves use the crouching list in `punishers.json`.

| Move | Name | Level | Startup | On block | Punish with |
|---|---|---|---|---|---|
| `1,2,4` | One Two Knee | mid | i11 | -10 | `1` |
| `f,n,d,df+2` | Wind God Fist | high | i11 | -10 | `1` |
| `d+4` | Crouch Shin Kick | low | i12 | -15 | `1+2` |
| `1,1,2` | Flash Claw Combo | mid | i13 | -17 | `1+2` |
| `df+4,4` | Tsunami Kick | mid | i13 | -15 | `1+2` |
| `b+2` |  | high | i14 | -13 | `1+2` |
| `ws2` | Alaya | mid | i14 | -12~-11 | `1+2` |
| `ws3` | Organ Wrecker | mid | i14 | -11 | `b+1` |
| `b,f+2,1` |  | mid | i14 | -10 | `1` |
| `d+3+4` | Double Lift Kicks | mid/mid | i15 | -15 | `1+2` |
| `f+4` |  | mid | i15 | -12 | `1+2` |
| `f+2,4` | 893P > Knee Kick | mid | i15 | -11 | `b+1` |
| `f,n,d,DF+4` |  | low | i16 | -23c | `1+2` |
| `db+3` | Crouch Spin Kick | low | i16 | -17 | `1+2` |
| `uf+3+4` | Hisou | mid/mid | i16 | -16 | `1+2` |
| `2,2` | Demon Backhand Spin | high | i17 | -13 | `1+2` |

## Lows to block crouching

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `db+1` | Crouch Jab | special_low | i10 | -5 |  |
| `d+2` | Crouch Straight | special_low | i11 | -4 |  |
| `d+4` | Crouch Shin Kick | low | i12 | -15 |  |
| `db+3` | Crouch Spin Kick | low | i16 | -17 |  |
| `f,n,d,DF+4` |  | low | i16 | -23c |  |
| `d+3` | Broken Plate | low | i18 | -12 | homing |
| `db+2` | Malicious Mace | low | i21 | -13 |  |

## Tracking or homing moves (sidestepping is unreliable)

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

## Moves that leave them plus on block (do not press buttons)

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `1` | Jab | high | i10 | +1 |  |
| `b+1+2` | Aratama Strike | mid | i20 | +3c |  |

## Throws and the break that answers them

| Throw | Startup | Break |
|---|---|---|
| `1+3` | i12 | 1/2 |
| `2+4` | i12 | 1/2 |
| `df+2+3` | i12 | 2 |
| `f,hcf+1+2` | i12 | 1+2 |
| `qcb+1+3` | i12 | 1 |
| `uf+1+2` | i12 | 1+2 |
