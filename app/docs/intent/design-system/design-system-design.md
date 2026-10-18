---
parent: high-level-design
prefix: DS
---

# Design system: Tatami

## Context and Design Philosophy

Tatami is the one visual system shared by the overlay and the main window. Its source of truth is the Paper file "Kumite — Tatami": the Foundations page defines the palette, type, belts and house rules, and the Overlay, Main window and States pages show them applied. The code mirrors that file. When a value in code and a value in Paper disagree, Paper wins and the code changes.

The mood is a calm dojo: the straw mat is the ground, the indigo border frames what matters, and belts show skill. Everything else stays quiet.

## Tokens

The tokens are the Paper file's design tokens, copied into a Tailwind v4 `@theme` block in `src/renderer/src/styles.css` under the same names: `--color-*`, `--font-*`, `--text-*`, `--font-weight-*`, `--tracking-*`, `--leading-*`, `--opacity-*`, `--container-*`, `--spacing-*` and `--radius-*`. Components use them through Tailwind utilities (`bg-surface`, `text-text-muted`, `w-sidebar`) or `var(--color-primary)`, never through raw hex values, except for the few translucent ink and white values Paper itself uses as literals (hairlines such as `#1D1B161F`).

| Role | Token | Value |
|---|---|---|
| Mat, the ground | `--color-bg` | `#E6E0C2` |
| Mat light, raised panels and inputs | `--color-surface` | `#F1ECD6` |
| Mat deep, tracks and skeletons | `--color-track` | `#CFC8A0` |
| Ink, text | `--color-text` | `#1D1B16` |
| Muted text | `--color-text-muted` | `#5C5744` |
| Indigo, the mat border | `--color-primary` | `#26365C` |
| Rust, only what the bot is targeting | `--color-bot` | `#B5462B` |
| Rust for text on the mat, same rule | `--color-bot-text` | `#AA4128` (4.5:1 on the mat; `--color-bot` reaches only 4.1:1 for small text) |
| Night (overlay ground, line, text, muted) | `--color-overlay*` | `#1A2034` at 90%, `#3A4A72`, `#EDE7CB`, `#B9B394` |
| Online | `--color-ok` | `#5BB86E` |
| Right call (a Paper literal, kept as a token) | `--color-good` | `#2E6B3B` |
| Belts | `--color-belt-*` | white, yellow, orange, green, blue, brown, black |

**Mat ground.** The main window and the between-round card sit on the mat: `--color-bg` with a faint weave, a repeating horizontal 1 px ink line at 3.5% opacity every 5 px.

## Type

Three families, all bundled with the app from `@fontsource` packages (Latin subsets only), so the app renders correctly without internet:

| Family | Token | Use | Weights |
|---|---|---|---|
| Dela Gothic One | `--font-display` | Page titles and one hero number per screen | 400 |
| Zen Kaku Gothic New | `--font-body` | Everything else; black (900) for numbers; 16 px minimum body | 400, 500, 700, 900 |
| IBM Plex Mono | `--font-mono` | Game notation, frame counts, chart axes; never labels | 400, 500, 600, 700 |

## House rules

From the Foundations page:

1. Rust means the bot is targeting it. Nothing else is rust.
2. One indigo frame per screen, around the thing that matters most.
3. Labels are sentence case. No tracked capitals, no colored edge stripes.
4. Every belt is drawn with its rank name next to it.
5. Every control shows a focus ring when focused from the keyboard: a 3 px mat-colored gap, then a 3 px indigo ring.

## Belts

A habit's mastery (0 to 1) and its `fixed` flag map to a belt rank:

| Rank | Mastery |
|---|---|
| White | below 0.15 |
| Yellow | 0.15 to 0.30 |
| Orange | 0.30 to 0.45 |
| Green | 0.45 to 0.60 |
| Blue | 0.60 to 0.75 |
| Brown | 0.75 and up, while not fixed |
| Black | fixed |

Black means the profile marks the habit fixed, whatever its mastery. A habit at 0.85 or above that is not fixed stays brown.

**Stripes.** Tape stripes show progress through the current rank, one per completed third, so a belt carries zero, one or two stripes. Brown's band runs from 0.75 to 0.85 for stripe purposes, and anything above 0.85 counts as its end. White and black belts carry no stripes. The rank name reads "Yellow belt, 1 stripe", "Orange belt, 2 stripes", "Blue belt", "Black belt".

**Drawing.** A belt is the Paper belt drawing: a 64 × 26 band with a knot and two tails, filled with the rank color and outlined in 35% black. Stripes are 3 × 8 ink bars near the right end (one at x 53; two at x 50 and 55). On the night ground of the overlay, the black belt is outlined in night text so it stays visible. A belt's history is drawn as 16 px rounded squares in rank colors, the white square outlined.

## Words

The services speak in keys; the app speaks in words. One module maps keys to the words the designs use:

- **Characters:** `devil_jin` Devil Jin, `kazuya` Kazuya, `king` King, `shaheen` Shaheen, `unknown` Opponent.
- **Habits** (situation keys from the learning system): `low_defense` Low blocks ("low-block habit"), `sidestep_dir` Sidestep direction ("sidestep habit"), `throw_break` Throw breaks ("throw-break habit"), `after_block` and `after_block:<move>` After you block ("after-block habit").
- **Situations** (stats and timeline keys): `neutral` Neutral, `wakeup` Wake-up, `whiff_punished` Whiff punished, `throw` Throws, `after_block:<move>` After blocking `<move>`, `low_defense` Low blocks, `sidestep_dir` Sidesteps.
- **Notation:** a compact move key becomes Tekken notation: a direction followed by buttons gets a plus (`df1` → `df+1`), and buttons pressed together are joined (`12` → `1+2`).
- **Option and action names:** underscores become spaces and the first letter is capitalized (`block_low` → Block low).
- **Anything else** is humanized the same way, so an unknown key still reads as words.

## Formats

- **Set time:** "Today, 2:41 PM" for today, "Oct 16, 9:12 PM" otherwise; "Today at 2:41 PM" in a sentence.
- **Duration:** minutes and seconds, "4:12".
- **Percent:** a 0 to 1 rate as a whole percent, "68%"; a missing rate (null) as an em dash.
- **Change since last set:** a signed whole number, "+6", or "Down 4" when it leads a sentence.
- **Share of a whole:** half, a third, a quarter, a fifth, when within 3 points of one; otherwise a whole percent.
- **Scores:** an en dash between numbers, "1–2".

## Components

| Component | Purpose |
|---|---|
| `Belt` | The belt drawing for a mastery and fixed flag, light or night variant |
| `BeltSquares` | A row of history squares, one per round |
| `Button` | Primary (indigo fill, night-text label) and quiet (text link in indigo) |
| `Toggle` | A 48 × 28 switch: indigo when on, mat deep when off |
| `Slider` | A 6 px track with an indigo fill and a 24 px mat-light thumb with an indigo border |
| `Select` | A native select drawn as the bordered field with an indigo chevron |
| `KeyCap` | A key shown as a raised cap, mono, indigo |
| `Chip` | A pill filter with a label and a mono count; selected chips fill indigo |
| `Meter` | A 12 px rounded bar on mat deep with an indigo or muted fill |
| `StatusDot` | A 10 px dot: online green, offline an outlined ring, unknown mat deep |
| `Skeleton` | Mat-deep blocks in the shape of the content they stand for |
| `EmptyState` | The mat illustration (a mat-light panel with indigo borders top and bottom), a headline, one line, and an optional status line |
| `OfflineBanner` | An indigo-framed strip naming the unreachable service, saying what the screen still shows, with a Try again button |
| Icons | The sidebar, chevron, arrow, play, microphone and unlinked icons, drawn as in Paper |

## State patterns

Every screen designs the same three states:

- **Loading:** skeleton blocks in the shape of the screen's content, never a spinner.
- **Empty:** the `EmptyState` pattern with copy that says what will fill the screen.
- **Offline:** the `OfflineBanner` above the content. When the screen still holds data from before the service went away, that data stays visible under the banner; when it holds none, the banner stands alone.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Styling | Tailwind v4 with the Paper tokens as its `@theme` | CSS Modules over a hand-written token stylesheet; inline styles | Paper exports Tailwind classes that already name these tokens (`bg-surface`, `w-sidebar`, `text-base/sm`), so screens port with exact values and little translation. A token edit in Paper is one `@theme` edit in code. |
| Fonts | Bundled from `@fontsource`, Latin subsets | Google Fonts at run time | The venue network is unreliable and the booth must work offline. Latin subsets keep the Japanese-capable Zen Kaku Gothic New small. |
| Where the belt thresholds live | In the app, from the Foundations page | A belt field from the brain or analytics | The thresholds are a visual convention the design owns, applied to a mastery number the contract already carries. This is threshold arithmetic the HLD allows. |
| Where display words live | One app module mapping keys to words | Labels sent by each service | The words are design copy ("Low blocks", "After blocking df+1") and change with the design, not with the learning system. Unknown keys still render as humanized words. |
| Select and slider controls | Native `select` and `input type=range`, styled | Custom listbox and slider components | Native controls bring keyboard support and accessibility with no extra code, and style closely enough to the Paper drawings. |

## Open Questions & Future Decisions

### Deferred
1. Motion: the Paper file defines no motion tokens. Transitions stay minimal (color and opacity, 150 ms) until it does.
2. A dark main window. Tatami is light; the night palette belongs to the overlay only.

## References

- Paper file "Kumite — Tatami": Foundations page; States page
- `../../high-level-design.md`: Design system component, tenets
