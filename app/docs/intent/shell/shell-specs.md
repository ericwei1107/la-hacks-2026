# Shell specs

Design: `shell-design.md`

## Service addresses

- [ ] **SHELL-ADDR-001**: The main process shall resolve one address each for the brain, replay and analytics services once at startup, before it creates any window.
- [ ] **SHELL-ADDR-002**: When resolving a service address, the main process shall use the first acceptable value from, in order: the service's variable in the process environment (`KUMITE_BRAIN_URL`, `KUMITE_REPLAY_URL` or `KUMITE_ANALYTICS_URL`), the same variable in `app/.env`, and the service's default.
- [ ] **SHELL-ADDR-003**: The service address defaults shall be `http://localhost:8765` for the brain, `http://localhost:8766` for replay and `http://localhost:8767` for analytics.
- [ ] **SHELL-ADDR-004**: The main process shall treat a service address variable set to an empty value as unset, without a warning.
- [ ] **SHELL-ADDR-005**: The main process shall accept a non-empty service address variable only when its value parses as an absolute URL with the `http:` or `https:` scheme.
- [ ] **SHELL-ADDR-006**: When the main process accepts a service address variable, it shall remove trailing slashes from the value and keep any path.
- [ ] **SHELL-ADDR-007**: If a non-empty service address variable is not acceptable, then the main process shall skip it and continue to the next source for that service.
- [ ] **SHELL-ADDR-008**: If the main process skips a service address variable as not acceptable, then it shall attach a warning to that service's resolved address that names the variable, its source (environment or `app/.env`) and the rejected value.
- [ ] **SHELL-ADDR-009**: If the main process skips a service address variable as not acceptable, then it shall print the same warning to the main process console.
- [ ] **SHELL-ADDR-010**: The main process shall record each resolved service address's source as `env`, `file` or `default`.
- [ ] **SHELL-ADDR-011**: The main process shall parse `app/.env` into a private object and shall not add its values to the process environment.
- [ ] **SHELL-ADDR-012**: If `app/.env` does not exist, then the main process shall resolve service addresses as if the file were empty, without a warning.
- [ ] **SHELL-ADDR-013**: If `app/.env` exists but cannot be read or parsed, then the main process shall resolve service addresses as if the file were empty and print a warning to the main process console.

## The bridge

- [ ] **SHELL-BRIDGE-001**: The preload script shall expose one object to every window's page as `window.kumite`, holding `platform` (the operating system platform as `process.platform` reports it), `services` and `speak`.
- [ ] **SHELL-BRIDGE-002**: The `window.kumite.services` object shall hold, for each of `brain`, `replay` and `analytics`, the resolved `url`, its `source`, and its `warning` when one exists.
- [ ] **SHELL-BRIDGE-003**: The preload script shall obtain `window.kumite.services` from the main process with one synchronous IPC call made while the preload runs, so the object is complete before any page script executes.
- [ ] **SHELL-BRIDGE-004**: The bridge shall pass to a window no value read from the process environment or `app/.env` other than the three resolved service addresses and their warnings.
- [ ] **SHELL-BRIDGE-005**: When a page calls `window.kumite.speak` with a text, the bridge shall pass the text to the main process's speak call over an asynchronous IPC call and resolve with that call's result.

## Windows

- [ ] **SHELL-WIN-001**: The main process shall open the main window at 1440 × 900 with a 1024 × 640 minimum, titled "Kumite", loading the renderer's `index.html`, and show it once its first frame is ready.
- [ ] **SHELL-WIN-002**: Both windows shall load the shared preload with context isolation on, Node integration off and the sandbox on.
- [ ] **SHELL-WIN-003**: When `KUMITE_OVERLAY` is `1` or `on` in the process environment or `app/.env`, the main process shall open the overlay window, loading the renderer's `overlay.html`; otherwise it shall not open the overlay window.
- [ ] **SHELL-WIN-004**: The overlay window shall cover the full bounds of the primary display and be frameless, transparent, shadowless and absent from the taskbar.
- [ ] **SHELL-WIN-005**: The overlay window shall stay on top at the `screen-saver` level and, on macOS, show on every workspace including full-screen ones.
- [ ] **SHELL-WIN-006**: The overlay window shall ignore all mouse events and shall not be focusable.
- [ ] **SHELL-WIN-007**: The overlay window shall leave content protection off, so screen capture records it.
- [ ] **SHELL-WIN-008**: The overlay window shall set its zoom factor to the primary display's width divided by 1920.
- [ ] **SHELL-WIN-009**: When the main window closes on Windows or Linux, the main process shall quit the app, closing the overlay window with it.
- [ ] **SHELL-WIN-010**: Both windows shall allow media to play without a user gesture.
- [ ] **SHELL-WIN-011**: The main window shall run with background throttling off.

## Implemented in

| Spec IDs | Entry point |
|---|---|
| SHELL-ADDR-001 | `src/main/index.ts` (the `app.whenReady` handler) |
| SHELL-ADDR-002, SHELL-ADDR-004 – SHELL-ADDR-013 | `src/main/services.ts` (`resolveServiceAddresses`) |
| SHELL-ADDR-003 | `src/shared/bridge.ts` (`DEFAULT_SERVICE_URLS`) |
| SHELL-BRIDGE-001 – SHELL-BRIDGE-004 | `src/preload/index.ts`, answered by `src/main/index.ts` (the `SERVICES_CHANNEL` handler) |
| SHELL-BRIDGE-005 | `src/preload/index.ts`, answered by `src/main/voice.ts` (`handleVoice`) |
| SHELL-WIN-001, SHELL-WIN-002, SHELL-WIN-009, SHELL-WIN-011 | `src/main/index.ts` (`createMainWindow`) |
| SHELL-WIN-010 | `src/main/index.ts` (`webPreferences`) |
| SHELL-WIN-003 – SHELL-WIN-008 | `src/main/index.ts` (`createOverlayWindow`), `src/main/services.ts` (`overlayEnabled`) |
