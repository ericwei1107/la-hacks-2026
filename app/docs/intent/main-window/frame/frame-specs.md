# Main window frame specs

Design: `frame-design.md`

## Sidebar

- [ ] **MAIN-FRAME-001**: The main window shall show the sidebar with the Kumite wordmark, the navigation rows Sessions, Replay analysis, Learning, Stats, Coach and Controls, and a status row for each of Brain, Replay and Analytics.
- [ ] **MAIN-FRAME-002**: When the player activates a navigation row by click, Enter or Space, the main window shall show that row's screen and mark the row as current.
- [ ] **MAIN-FRAME-003**: The sidebar shall draw the current screen's row with a `--color-bg` fill and a bold `--color-primary` label, and every other row with an `--color-overlay-muted` label.
- [ ] **MAIN-FRAME-004**: Each sidebar status row shall show its service's `StatusDot`, and while that service is offline its label shall read "<Service> offline" in bold.
- [ ] **MAIN-FRAME-005**: When the main window opens, it shall show the Sessions screen.

## Selected set

- [ ] **MAIN-FRAME-010**: The frame shall hold one selected set shared by the Replay analysis, Learning, Stats and Coach screens.
- [ ] **MAIN-FRAME-011**: While the player has not chosen a set in this window, the selected set shall be the newest set in the brain's set list.
- [ ] **MAIN-FRAME-012**: When the player chooses a set in the set picker or opens a set from the Sessions screen, the frame shall make it the selected set and keep it selected until the player chooses another.
- [ ] **MAIN-FRAME-013**: When a `round_summary` for the selected set arrives on the brain's coach stream, the frame shall refetch that set's session, recording, stats, learning metrics and report.

## Page header and set picker

- [ ] **MAIN-FRAME-020**: Each screen shall show its title in the display face at 40 px at the top left of the screen area.
- [ ] **MAIN-FRAME-021**: The Replay analysis, Learning, Stats and Coach screens shall show the set picker at the right of the page header.
- [ ] **MAIN-FRAME-022**: The set picker shall list the brain's sets newest first, each labelled with its start time followed by "set".
- [ ] **MAIN-FRAME-023**: If the brain's set list cannot be loaded while a set is selected, then the set picker shall read "Last saved set" and list no other sets.
- [ ] **MAIN-FRAME-024**: While the brain's set list is loaded and empty, the frame shall not show the set picker.

## Moving between screens

- [ ] **MAIN-FRAME-030**: The frame shall let a screen open another screen with an optional set and an optional focus of round and frame, selecting the set when one is given.

## Integration readout

- [ ] **MAIN-FRAME-040**: When the main window's address ends in `#integration`, the window shall show the plain integration readout of service addresses, service states and stream states instead of the frame.
