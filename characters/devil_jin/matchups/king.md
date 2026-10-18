# Devil Jin vs King

What Devil Jin should expect from King, and what Devil Jin can punish. Generated from `characters/king/moves.json` and `characters/devil_jin/punishers.json`.

## What to expect

- Throw-based grappler: command throws, chain grabs and mid pokes carry the offence.
- Command throws have different break inputs (qcf+1 breaks with 1, df+2+3 with 2, db+2+3 with 1+2 per field observation), so a player who always breaks the same way can be thrown with the other ones. This is the cleanest demonstration of the throw-break habit.
- Fast jabs (1 and 2 are i10) and the plus-on-block jabs let King keep the turn, then mix throws with mid pokes.

## Punishable on block

`Punish with` is Devil Jin's best standing punisher for that gap (the move's on-block value, clamped to i10 to i20). Against crouching or low moves use the crouching list in `punishers.json`.

| Move | Name | Level | Startup | On block | Punish with |
|---|---|---|---|---|---|
| `d+4` |  | low | i14 | -15 | `b+1+3` |
| `df+4` |  | low | i14 | -14 | `df+1` |
| `f,F+4` | Konvict Kick | mid/(t) | i15 | -15 | `b+1+3` |
| `ub+4` |  | mid | i15 | -13 | `df+1` |
| `uf+4` | Jumping Knee Lift | mid | i15 | -13 | `df+1` |
| `ws2,2` | Round Trip Chop | mid | i15 | -12 | `b+1` |
| `d+1,2` | Jab > Uppercut | mid | i15 | -11 | `2` |
| `f+2` |  | mid | i15 | -11 | `2` |
| `d+3+4` |  | low | i16 | -25 | `b+1+3` |
| `b+3` | Toll Kick | high | i16 | -10 | `2` |
| `d+3` | Stomp | low | i17 | -12 | `b+1` |
| `f,f,n,2` | Stomach Smash / Jaguar Hammer | low/(t) | i18 | -13 | `df+1` |
| `1+2` |  | mid | i18 | -11 | `2` |
| `ws1+2` | Snap Uppercut | mid | i18 | -10 | `2` |
| `b+1,2` | Quick Hook > Uppercut | high | i19 | -13 | `df+1` |
| `df+1,2` | Elbow Sting | mid | i20 | -10 | `2` |

## Lows to block crouching

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `d+1` |  | special_low | i10 | -5 |  |
| `d+2` |  | special_low | i11 | -4 |  |
| `d+4` |  | low | i14 | -15 |  |
| `df+4` |  | low | i14 | -14 |  |
| `d+3+4` |  | low | i16 | -25 |  |
| `d+3` | Stomp | low | i17 | -12 |  |
| `f,f,n,2` | Stomach Smash / Jaguar Hammer | low/(t) | i18 | -13 |  |
| `db+3` | Crouching Low Kick | low | i23 | -14 | left |

## Tracking or homing moves (sidestepping is unreliable)

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `db+3` | Crouching Low Kick | low | i23 | -14 | left |
| `df+3` |  | mid | i14 | -9 | right |
| `f+4` | Rolling Sobat | mid | i18 | -9 | homing |
| `f,F+1` | Jaguar Hook | mid | i20 | -5 | homing |
| `uf+1` | Water Parting Chop | high | i20 | -3 | homing |
| `ws2` |  | mid | i14 | -9 | homing |

## Moves that leave them plus on block (do not press buttons)

| Move | Name | Level | Startup | On block | Tracking |
|---|---|---|---|---|---|
| `1` | Jab | high | i10 | +1 |  |
| `2` | Right Jab | high | i10 | +1 |  |
| `f+1+4` | Body Check | mid | i17 | +3 |  |
| `b+4` | Disgraceful Kick | high | i17 | +2 |  |
| `f,f,F+3` | Strong Knee | mid | i20 | +3 |  |

## Throws and the break that answers them

| Throw | Startup | Break |
|---|---|---|
| `1+3` | i12 | 2 |
| `2+4` | i12 | not stated |
| `b+1+2` | i12 | not stated |
| `d+1+3` | i12 | not stated |
| `d+1+4` | i12 | not stated |
| `d+2+4` | i12 | not stated |
| `db+2+3` | i12 | 1+2 |
| `db,n,f+2+4` | i11 | not stated |
| `df+1+3` | i32 | not stated |
| `df+2+3` | i12 | 2 |
| `df+2+4` | i32 | not stated |
| `f,f,F+2+4` | i10 | not stated |
| `f,hcf+1` | i10 | not stated |
| `f,hcf+2` | i12 | not stated |
| `qcb+1+2` | i11 | not stated |
| `qcb+1+3` | i14 | not stated |
| `qcf+1` | i11 | 1 |
| `uf+1+2` | i12 | not stated |
