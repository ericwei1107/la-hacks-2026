---
parent: high-level-design
prefix: SHELL
---

# Shell

## Context and Design Philosophy

The shell is the Electron main process plus the preload bridge that every app window loads. It does the privileged work a page cannot or should not do, while the windows call the services themselves (HLD, Key Design Decisions). This design covers resolving the three service addresses, handing them to each window over the bridge, and creating the two windows.

Two principles:

- **The bridge carries an allow-list.** The main process reads the environment and `app/.env`, which also hold secrets such as the ElevenLabs key. A window receives the three resolved addresses and the platform name, named one by one, and nothing else from those sources. The voice calls carry text in and audio out; the key never crosses.
- **One app run, one set of addresses.** Addresses are resolved once when the main process starts. The overlay and the main window always point at the same services; pointing somewhere else means restarting the app.

## Service addresses

| Service | Default | Override variable |
|---|---|---|
| brain | `http://localhost:8765` | `KUMITE_BRAIN_URL` |
| replay | `http://localhost:8766` | `KUMITE_REPLAY_URL` |
| analytics | `http://localhost:8767` | `KUMITE_ANALYTICS_URL` |

The variable names are the ones `contracts/api.md` defines.

Each address is resolved independently, first acceptable source wins:

1. **The process environment**, e.g. `KUMITE_BRAIN_URL=http://192.168.50.2:8765 npm run dev`.
2. **`app/.env`**, parsed by the main process into a private object with Node's `util.parseEnv`. Its values are never copied into the process environment. A missing file counts as empty. A file that cannot be read or parsed also counts as empty, and the main process prints a warning to its console.
3. **The default.**

A variable set to an empty value counts as unset. A value is acceptable when it parses as an absolute URL whose scheme is `http:` or `https:`. Trailing slashes are removed and any path prefix is kept, so `http://host:8765/kumite` stays as written. An unacceptable value is skipped and resolution falls through to the next source. The skipped value is kept as a warning on the resolved address (which variable, which source, what it said), so the service status view can show why the app is not pointed where the user expected. The main process also prints the warning to its console.

Each resolved address records its source: `env`, `file` or `default`.

Moving from the mock services to Sahil's laptop means setting the three variables to the laptop's address, in `app/.env` or in the launching shell, and restarting the app.

## The bridge

Every window loads the same preload script, which exposes one object to the page as `window.kumite`:

```ts
window.kumite = {
  platform: 'darwin',
  services: {
    brain:     { url: 'http://192.168.50.2:8765', source: 'file' },
    replay:    { url: 'http://localhost:8766',    source: 'default',
                 warning: 'KUMITE_REPLAY_URL in the environment is not an http(s) URL: "192.168.50.2:8766"' },
    analytics: { url: 'http://localhost:8767',    source: 'default' }
  },
  speak: (text) => Promise<SpeakResult>,
  transcribe: (recording, mimeType) => Promise<TranscribeResult>
}
```

The preload asks the main process for `services` over one synchronous IPC call while it runs, so the object is complete before any page script executes. The service clients can then build every URL at module load without waiting.

`speak` and `transcribe` carry the voice component's calls: the text or the recording goes to the main process over an asynchronous `ipcRenderer.invoke`, and the clip, the transcript or a failure reason comes back (voice design). Only the data and the result cross; the ElevenLabs settings stay in the main process. The main process also answers the windows' microphone permission requests (voice design).

A page opened outside Electron, such as the renderer dev server in a plain browser, has no `window.kumite`. The service clients design covers that case.

## Windows

The main process opens two windows from the same renderer build, both with the shared preload, context isolation, no Node integration, and the sandbox on. Both let audio play without a user gesture: the main window speaks the coach's tip between rounds while the player's hands are on the game, possibly before anyone has clicked it (voice design).

**Main window.** 1440 × 900 by default, 1024 × 640 at least, titled "Kumite", shown once its first frame is ready. It loads the renderer's `index.html`. Background throttling is off: during a set the game covers it, and it still has to follow the round break and speak the coach's tip on time (voice design). Closing it quits the app on Windows and Linux, overlay included; on macOS the app stays in the dock and reopens the main window when activated.

**Overlay window, off by default.** The game screen belongs to the game (HLD tenet), so the overlay opens only when `KUMITE_OVERLAY` is `1` or `on`, in the environment or `app/.env`. When on, it loads the renderer's `overlay.html` and is drawn over Tekken 8:

- It covers the full bounds of the primary display, frameless, transparent, without a shadow, and out of the taskbar.
- It stays on top of other windows at the `screen-saver` level, and on macOS on every workspace, including full-screen ones.
- It ignores every mouse event, so each click reaches the game below, and it never takes focus.
- It is visible to screen capture: content protection stays off.
- It scales the page so the 1920 × 1080 design space fills the display: the zoom factor is the display width over 1920.


## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Where address overrides come from | Process environment, then `app/.env`, then defaults | Process environment only; an in-app address setting saved in Electron's user data folder | `app/.env` makes the venue switch one edited file, the same file the main process already reads for the voice key. The environment still wins, so a one-off launch can point elsewhere without editing the file. An in-app setting needs a designed settings screen and a persistence story, while the HLD fixes the addresses as one setting the main process reads. |
| How `app/.env` is read | Parsed into a private object with `util.parseEnv` | Loading it into `process.env` (`process.loadEnvFile`, `dotenv`) | Loading the file into the process environment places the ElevenLabs key in an object that later code could forward wholesale. A private parse keeps the bridge's allow-list the only path out. Electron 44 bundles Node 24, which has `util.parseEnv`, so no dependency is added. |
| When addresses are resolved | Once, at main-process startup | On every window load; watching `app/.env` for edits | A single resolution guarantees the overlay and the main window never point at different brains. Restarting the app costs seconds during integration. |
| How a window receives its addresses | Synchronous IPC from the preload | Asynchronous `invoke` from page code; `webPreferences.additionalArguments` read from `process.argv` | Synchronous delivery means `window.kumite.services` exists before page code runs, so the clients need no asynchronous start-up. The payload is three short strings, sent once per window. Reading `process.argv` inside a sandboxed preload is a less familiar path for the next reader. |
| An unacceptable override | Skip it, fall through to the next source, keep it as a warning | Refuse to start; pass the bad value through so every request to that service fails | The app stays usable, and the status view still says what went wrong. A refusal to start is worse at a booth than a visible warning. |
| Overlay window size | The primary display's full bounds, page zoomed from 1920 × 1080 | A window sized to the HUD and card only; the game window's bounds | A full-display window keeps the Paper coordinates valid at any resolution. Finding the game window would need native window enumeration, and the game runs borderless on the primary display. |
| Overlay focus and input | Never focusable, ignores all mouse events | Forwarding mouse moves for hover effects | The overlay has nothing to click; any focus or input it took would leave the game mid-round. |
| Turning on the overlay | Off by default; `KUMITE_OVERLAY=1` or `on` | On by default; a menu item | During a set the game screen belongs to the game, and the coach's tip is spoken by the main window. A variable read from the same sources as the addresses keeps the overlay one setting away for a demo that wants it. |
| Main window in the background | Background throttling off | Chromium's default throttling | Tekken covers the main window during a set. Throttled timers would delay the end of a round break and the voice that depends on it. |

## Open Questions & Future Decisions

### Deferred
1. The global push-to-talk key, including hold-to-talk while the game has focus (HLD open question).
2. Choosing the display the overlay covers, for a game on a secondary display.

## References

- `../../high-level-design.md`: Key Design Decisions (windows call the services directly; secrets stay in the main process; service addresses are one setting)
- `../../../../contracts/api.md`: service ports and address variables
- `../service-clients/service-clients-design.md`: the consumer of `window.kumite.services`
