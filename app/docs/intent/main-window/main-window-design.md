---
parent: high-level-design
prefix: MAIN
---

# Main window

## Context and Design Philosophy

The main window is where a player goes before and after a set: to read what happened, see whether the bot learned, ask the coach, and set up the next set. Its design is the Main window and States pages of the Paper file "Kumite — Tatami", drawn at 1440 × 900 in the Tatami system (design-system).

The window is one frame with six screens. The frame holds what every screen shares: the indigo sidebar with navigation and service status, the page header, and the set the screens are about. Each screen is its own leaf below this node.

## Layout

The sidebar is 248 px wide (`--container-sidebar`), indigo, with the wordmark at the top, the six screens below it, and the three services' status at the bottom. The rest of the window is the screen, on the mat ground, padded 56 px left and right, 36 px top and 40 px bottom, and scrolling vertically when its content is taller than the window. Screens are designed at 1440 × 900 and stretch their widest column to fill other window sizes down to the 1024 × 640 minimum.

## The selected set

Four screens (Replay analysis, Learning, Stats, Coach) are about one set at a time: the **selected set**. The frame owns it, and every screen reads the same one, so moving between screens never loses the set the player is looking at. The set picker in those screens' headers changes it. Opening a set from the Sessions screen, or following a set's "Replay analysis" button, also changes it.

Until the player picks a set, the selected set follows the newest set the brain lists, so a set that just finished is the one on screen. Once the player picks a set, it stays selected until they pick another.

## Live refresh

A screen showing the set being played refreshes its set data when a `round_summary` for that set arrives on the brain's coach stream. That is the moment the learning metrics, stats and recording gain a round. Screens showing an older set do not refresh.

## Screens

| Screen | Leaf | Services it reads |
|---|---|---|
| Sessions | `sessions/` | brain |
| Replay analysis | `replay-analysis/` | replay, brain |
| Learning | `learning/` | analytics, brain |
| Stats | `stats/` | analytics, brain |
| Coach | `coach/` | replay, brain |
| Controls | `controls/` | brain |

The frame and its shared parts are the `frame/` leaf.

A screen whose services are unreachable shows the offline state for the first unreachable service in its list, per the design system's state patterns.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Navigation | Screen state held in the frame | A URL router library | Six fixed screens and no deep links. A router adds a dependency and URL handling the window never shows. |
| Selected set scope | One set shared by every screen | A picker per screen with its own choice | The Paper design repeats the same picker label on each screen. The player follows one set through analysis, learning, stats and coaching. |
| Following the newest set | Until the player picks one | Always the newest; never automatically | The booth flow ends a set and opens the app: the new set must be on screen without a click. A deliberate pick must not jump away when a new set starts. |

## References

- Paper file "Kumite — Tatami": Main window and States pages
- `../design-system/design-system-design.md`
- `../service-clients/service-clients-design.md`
