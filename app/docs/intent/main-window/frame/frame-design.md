---
parent: main-window
prefix: MAIN-FRAME
---

# Main window frame

## Context and Design Philosophy

The frame is everything around a screen: the sidebar, the page header, the set picker, and the selected set itself (main-window). It is drawn identically on every Main window artboard in Paper.

## Sidebar

- **Wordmark:** the Kumite mark (four interlocking indigo-outlined bars around a yellow square) and "Kumite" in the display face, night text.
- **Navigation:** Sessions, Replay analysis, Learning, Stats, Coach, Controls, each a 44 px row with its icon. The current screen's row fills with the mat color and its label turns bold indigo; the others are night-muted. Rows are buttons, reachable by Tab and activated by Enter or Space.
- **Service status:** below a hairline at the bottom, one row per service, Brain, Replay and Analytics, each with a `StatusDot`. An offline service's label reads "Brain offline" in bold.

## Page header

Each screen's title in the display face (40 px). The Replay analysis, Learning, Stats and Coach screens add the set picker at the right.

## Set picker

A select drawn as the bordered Paper picker. Its options are the brain's sets, newest first, each labelled with its start time and "set" ("Today, 2:41 PM set"). Choosing an option changes the selected set.

When the brain's set list cannot be loaded but a set is still selected from earlier, the picker reads "Last saved set" and offers no other options. When there are no sets, the picker is not shown.

## Keeping sets fresh

The frame refetches what the brain and analytics hold about a set when it changes during play, whichever set is selected:

- A round summary for any set refetches the set list, and that set's session, recording, stats, learning metrics, report and the trends.
- A new live set on the state stream (a match starting) refetches the set list, so the new set appears without waiting for its first round to end.
- When the round stops being live (states stop for 2 seconds, as at the end of a set), the frame refetches the set list and the live set's session, recording, stats and learning, which picks up the end time and result the brain writes as the set closes.
- After a round summary for round n, the brain and analytics may still be writing that round to disk. While that set's stats or learning lack round n, the frame refetches them every 2 seconds for up to 20 seconds, and screens can show that round as still being saved.

## Moving between screens

- The Sessions screen's "Replay analysis" button selects that set and opens Replay analysis.
- A citation chip in the Coach screen opens Replay analysis at that round and frame.
- The frame passes an optional focus (round and frame) to Replay analysis; the screen decides what to do with it.

## Integration readout

The plain service and stream readout written before the screens existed stays available at the `#integration` address of the main window, outside the frame, for checking a new service setup. It is not linked from the sidebar.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Where the service status lives | The sidebar footer, on every screen | A separate status screen | Paper places it in the sidebar, where a stopped service is visible from any screen. |
| Keeping the integration readout | At `#integration`, unlinked | Deleting it now that the screens exist | It shows raw addresses, address warnings and stream states that the designed screens do not, which helps when pointing the app at a new machine. |

## References

- Paper file "Kumite — Tatami": the Sidebar and Page header frames on the Main window page; Learning · Offline on the States page
- `../main-window-design.md`
