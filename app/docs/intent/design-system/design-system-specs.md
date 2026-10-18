# Design system specs

Design: `design-system-design.md`

## Tokens and type

- [ ] **DS-TOKEN-001**: The renderer stylesheet shall define every design token of the Paper file "Kumite — Tatami" in a Tailwind v4 `@theme` block under the token's Paper name and value.
- [ ] **DS-TOKEN-002**: The main window and the between-round card shall paint the mat ground: `--color-bg` overlaid with a repeating horizontal 1 px line of ink at 3.5% opacity every 5 px.
- [ ] **DS-TYPE-001**: The app shall load Dela Gothic One (400), Zen Kaku Gothic New (400, 500, 700, 900) and IBM Plex Mono (400, 500, 600, 700) from font files bundled with the app, using Latin subsets, and shall make no network request for fonts.
- [ ] **DS-RULE-001**: The app shall use `--color-bot` (rust) only for elements that show what the bot is targeting.
- [ ] **DS-RULE-002**: When a control receives keyboard focus, it shall show a focus ring made of a 3 px `--color-bg` gap followed by a 3 px `--color-primary` ring.

## Belts

- [ ] **DS-BELT-001**: When a habit is marked fixed, the app shall show it as a black belt, whatever its mastery.
- [ ] **DS-BELT-002**: When a habit is not marked fixed, the app shall choose its belt by mastery: white below 0.15, yellow from 0.15, orange from 0.30, green from 0.45, blue from 0.60, and brown from 0.75 upward.
- [ ] **DS-BELT-003**: For a yellow, orange, green or blue belt, the app shall show one stripe per completed third of the belt's 0.15-wide mastery band, so zero, one or two stripes.
- [ ] **DS-BELT-004**: For a brown belt, the app shall count stripes over the band 0.75 to 0.85, treating mastery above 0.85 as the end of the band.
- [ ] **DS-BELT-005**: The app shall show no stripes on white or black belts.
- [ ] **DS-BELT-006**: Wherever the app draws a belt, it shall also show its rank name in words ("Yellow belt, 1 stripe", "Blue belt", "Black belt").
- [ ] **DS-BELT-007**: The `Belt` component shall draw the Paper belt (a 64 × 26 band, knot and tails in the rank color, outlined in 35% black, stripes as 3 × 8 ink bars at x 53, or x 50 and 55).
- [ ] **DS-BELT-008**: Where the `Belt` component is drawn on the overlay's night ground, it shall outline the black belt in `--color-overlay-text`.
- [ ] **DS-BELT-009**: The `BeltSquares` component shall draw one 16 px rounded square per round in that round's belt color, outlining white squares in ink at 30%.

## Words and formats

- [ ] **DS-WORD-001**: The app shall show character keys as Devil Jin, Kazuya, King, Shaheen, and Opponent for `unknown`.
- [ ] **DS-WORD-002**: The app shall show habit keys as Low blocks (`low_defense`), Sidestep direction (`sidestep_dir`), Throw breaks (`throw_break`) and After you block (`after_block` with or without a move), with the short forms low-block, sidestep, throw-break and after-block for use inside sentences.
- [ ] **DS-WORD-003**: The app shall show situation keys as Neutral (`neutral`), Wake-up (`wakeup`), Whiff punished (`whiff_punished`), Throws (`throw`) and After blocking `<move>` (`after_block:<move>`), and shall show any habit key used as a situation by its habit name.
- [ ] **DS-WORD-004**: When the app shows a compact move key, it shall write it in Tekken notation, putting a plus between a leading direction and its buttons (`df1` as df+1) and between buttons pressed together (`12` as 1+2).
- [ ] **DS-WORD-005**: When the app shows a key that has no listed word, it shall replace underscores with spaces and capitalize the first letter.
- [ ] **DS-FMT-001**: The app shall show a set's start time as "Today, h:mm AM/PM" for today and "Mon D, h:mm AM/PM" for other days.
- [ ] **DS-FMT-002**: The app shall show a duration as minutes and two-digit seconds ("4:12").
- [ ] **DS-FMT-003**: The app shall show a 0 to 1 rate as a whole percent, and a null rate as an em dash.
- [ ] **DS-FMT-004**: The app shall show a share of a whole as "half", "a third", "a quarter" or "a fifth" when it lies within 0.03 of that fraction, and as a whole percent otherwise.

## Components and states

- [ ] **DS-COMP-001**: The design system shall provide the `Belt`, `BeltSquares`, `Button`, `Toggle`, `Slider`, `Select`, `KeyCap`, `Chip`, `Meter`, `StatusDot`, `Skeleton`, `EmptyState` and `OfflineBanner` components and the Paper icons, drawn as in the Paper file.
- [ ] **DS-COMP-002**: The `Toggle`, `Slider` and `Select` components shall be operable from the keyboard.
- [ ] **DS-COMP-003**: The `StatusDot` component shall show a filled `--color-ok` dot for online, a 2 px `--color-overlay-muted` ring for offline, and a `--color-track` dot for unknown.
- [ ] **DS-STATE-001**: While a screen's data is loading for the first time, the screen shall show skeleton blocks in the shape of its content.
- [ ] **DS-STATE-002**: The `EmptyState` component shall show the mat illustration, a headline, one line of copy, and an optional status line with a dot.
- [ ] **DS-STATE-003**: The `OfflineBanner` component shall name the unreachable service in bold, say what the screen still shows, and offer a Try again button.
- [ ] **DS-STATE-004**: While a screen's service is unreachable and the screen holds data received earlier, the screen shall keep showing that data below the `OfflineBanner`.

## Implemented in

All paths are under `src/renderer/src/`.

| Spec IDs | Entry point |
|---|---|
| DS-TOKEN-001, DS-TOKEN-002, DS-RULE-002 | `styles.css` |
| DS-TYPE-001 | `fonts.ts` |
| DS-RULE-001 | every component that draws `--color-bot`; no single entry point |
| DS-BELT-001 – DS-BELT-006 | `design/belts.ts` (`beltFor`, `beltName`) |
| DS-BELT-007 – DS-BELT-009 | `design/Belt.tsx` (`Belt`, `BeltSquares`) |
| DS-WORD-001 – DS-WORD-005 | `design/words.ts` |
| DS-FMT-001 – DS-FMT-004 | `design/format.ts` |
| DS-COMP-001, DS-COMP-002 | `design/controls.tsx`, `design/icons.tsx`, `design/states.tsx` |
| DS-COMP-003, DS-STATE-001 – DS-STATE-003 | `design/states.tsx` |
| DS-STATE-004 | `main-window/Screen.tsx` (`ScreenBanner`), with the query cache keeping earlier data |
