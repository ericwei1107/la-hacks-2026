---
parent: high-level-design
prefix: VOICE
---

# Voice

## Context and Design Philosophy

The coach speaks and listens through ElevenLabs. The coach speaks in two places: during a set, from the main window with nothing on screen, each tip the moment the brain sends it; and in the Coach screen after a set, where the player can also ask a question by holding to talk. A tip is only useful whole, so a line that has started always finishes, even when the next round starts; keeping tips short enough to fit the round-end screen is the replay service's side of this.

The main process makes every ElevenLabs call, because it holds the key (HLD, secrets stay in the main process). The windows play and record audio, because only a page has the audio and microphone APIs. The two meet over two bridge calls: speak, which streams a text's audio to the window as it is made, and transcribe, which turns a recording into text.

Voice is an addition, never a dependency. Every line the coach speaks is also on screen, and every voice failure leaves the app as it is without voice: the text still shows, and a typed question still works.

## Settings

| Setting | Read from | Needed for |
|---|---|---|
| `ELEVENLABS_API_KEY` | The process environment, then `app/.env` | Speaking and transcribing |
| `ELEVENLABS_VOICE_ID` | The process environment, then `app/.env` | Speaking |

The main process reads both once at start, from the same sources and in the same order as the service addresses (shell). An empty value counts as unset. Neither value ever crosses the bridge. The coach's voice is chosen in the ElevenLabs account and set once per machine; there is no default voice.

The brain config's `voice` flag turns speaking on and off for both windows; turning it off drops the lines waiting to play and lets a line already playing finish. It does not affect listening: holding to talk is the player's own action.

When a setting is unset at start, the main process prints which one to its console, so a silent coach at the booth has a visible cause. It prints each failed ElevenLabs call there too.

## Main process: the ElevenLabs calls

**Speak.** `POST https://api.elevenlabs.io/v1/text-to-speech/<voice id>/stream?output_format=mp3_44100_128` with the `xi-api-key` header and the body `{ "text", "model_id", "voice_settings" }`. The model is `eleven_flash_v2_5`, the lowest-latency model; if ElevenLabs refuses it with 400, 403, 404 or 422, the main process prints a warning, repeats the request with `eleven_turbo_v2_5`, and uses that model for the rest of the run. `voice_settings` is the voice's stored settings with `speed` set to 1.15: the main process reads them once at start from `GET https://api.elevenlabs.io/v1/voices/<voice id>/settings`, dropping null values, and sends `speed` alone if that read fails or takes longer than 3 seconds. Each MP3 chunk goes to the asking window as it arrives, and the call resolves when the stream ends. It gives up when no response or chunk has arrived for 6 seconds.

**Transcribe.** `POST https://api.elevenlabs.io/v1/speech-to-text` with the `xi-api-key` header and a multipart body: `model_id` `scribe_v2`, `language_code` `en`, and the recording as `file`. The response's `text`, trimmed, comes back to the asking window. The call gives up after 10 seconds.

Both calls answer with a result rather than throwing: success (with the text, for transcribe), or a failure with one of these reasons.

| Reason | When | Shown to the player as |
|---|---|---|
| `not_configured` | A setting the call needs is unset; ElevenLabs is not contacted | "Voice isn't set up on this machine." |
| `rejected` | ElevenLabs answered with a non-2xx status | "ElevenLabs refused the request (<status>)." |
| `network` | The request could not be made or was cut off | "Can't reach ElevenLabs." |
| `timeout` | No answer within the call's limit | "ElevenLabs took too long." |

A failed speak is silent, apart from any audio that had already arrived: the line is already on screen. A failed transcribe tells the player why, because they are waiting for their question to appear.

## The bridge

The bridge gains two calls on `window.kumite`, carried over `ipcRenderer.invoke`:

- `speak(text, onChunk)` → each MP3 chunk passed to `onChunk` as it arrives, then success or a failure reason once the stream ends. Chunks travel on their own channel tagged with a per-window stream number and end with an end marker; the call resolves only after the end marker, so no chunk lands after it.
- `transcribe(recording, mimeType)` → the text, or a failure reason.

The shell owns the bridge and its allow-list; this design owns what the two calls do. In a plain browser there is no bridge, so voice is unavailable there and the app runs text-only.

## Speaking: the voice player

Each window has one voice player, a queue that plays one line at a time, in the order asked:

- Asked to speak, it adds the line to the end of the queue and starts its speak call at once, so a waiting line's audio is already arriving while the line before it plays.
- The line at the head of the queue starts playing on its first chunk, through Media Source Extensions (`audio/mpeg`), and keeps taking chunks as they arrive. Where Media Source Extensions do not support `audio/mpeg`, it waits for the whole clip instead.
- Nothing stops a line once it is playing: not a new line, a round start, a state update, a screen change, or a recording. When it ends, the next line starts.
- A line whose speak call fails before any audio arrives is skipped.
- It reports whether it is speaking, and whose line it is: each request carries a tag naming its caller (the round tip, or one Coach screen answer). A screen shows its speaking indicator only for its own line.
- It ignores requests to speak while the brain config's `voice` is not `true`, and when the bridge is missing it plays nothing.

Chromium blocks sound from a page the user has not interacted with, and between rounds the player's hands are on the game, perhaps before anyone has clicked the main window. So both windows are created with autoplay allowed without a user gesture, and the main window keeps running at full speed while the game covers it (shell).

**Coach tips (main window).** The main window speaks every `coach` record from the brain's coach stream the moment it arrives, with no wait for the round break or any card. Two tips that arrive close together play one after the other. Nothing is shown: the game screen belongs to the game, and the main window is behind it. The overlay, when turned on, shows its card silently, so there is only ever one voice.

**Coach screen.** When an answer arrives, the screen speaks it through the same voice player, so it queues behind a line already playing and plays to the end like any tip. Asking another question, holding to talk, switching sets or leaving the screen does not stop it. While an answer is being spoken, its "Coach" label is followed by a 64 × 20 indigo waveform and "Speaking" at 14 px bold in indigo.

## Listening: hold to talk (main window)

The player asks the coach by voice on the Coach screen, in either of two ways:

- **Hold the "Hold to talk" button.** Recording starts on press and stops on release, or when the pointer leaves the button or is cancelled.
- **Hold the push-to-talk key** while the main window has focus, the Coach screen is showing and focus is not in the text field (so the key can still be typed). Key repeats are ignored.

While recording, the button reads "Listening…". On release, a recording shorter than 300 ms is thrown away without a request (a tap, not a question). A longer one is transcribed while the button reads "Transcribing…", and the text is sent as a question exactly as if it had been typed. Recording stops by itself after 30 seconds and is transcribed as if released.

Starting to record leaves the coach's voice playing. A transcript that arrives after the player has switched sets or left the Coach screen is dropped, so a question never lands in a conversation it was not asked in. The recording is the microphone's audio in the browser's default `MediaRecorder` format (WebM with Opus in Electron), which Scribe accepts.

When the transcript is empty, a muted line under the input bar reads "Didn't catch that. Hold the key and try again." When the microphone or the call fails, the line reads "Couldn't hear you. <reason>", with "Microphone access is off. Allow it in System Settings → Privacy & Security → Microphone." for a refused microphone. The line clears on the next attempt or the next typed question.

Hold to talk is unavailable, and the button drawn disabled, under the same conditions as the text field (replay service offline, answer pending), and in a plain browser. While a recording is being transcribed, new presses are ignored.

**Microphone permission.** The main process grants microphone requests from the app's own pages and refuses every other media request. On macOS it asks the system for microphone access the first time a recording starts.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| How a clip reaches the window | ElevenLabs' streaming endpoint, chunks over IPC into Media Source Extensions, playing from the first chunk | The whole MP3 over one bridge call; a privileged custom protocol the audio element streams from | Sound starts about 200 ms after the request instead of after the whole clip is made. IPC chunks reuse the existing bridge; a custom protocol needs a privileged scheme registered before the app is ready. |
| Speech model | `eleven_flash_v2_5`, falling back to `eleven_turbo_v2_5` when the account refuses it | `eleven_multilingual_v2` | Lowest listed latency; the coach speaks English, and the round-end window is short. Turbo v2.5 is the next fastest. |
| Speaking speed | 1.15 on the voice's stored settings | The voice's stored speed | Round tips have to fit the round-end screen; 1.15 is faster while still clear, and ElevenLabs allows up to 1.2. Keeping the stored stability and similarity keeps the voice as chosen. |
| Lines that overlap | A queue: every line plays to the end, in order | The newest line replaces the one playing | A tip cut in half is worse than one heard a few seconds late, and tips close together are rare and short. |
| Transcription | One `scribe_v2` request on release | `scribe_v2_realtime` streaming while the key is held | Questions are a sentence or two; one request after release is one call with no socket to manage. |
| Where hold to talk works | The main window, while it has focus | A global key while the game has focus | Electron's global shortcuts report presses but not releases, so holding a key over the game needs a native keyboard hook, a compiled dependency on the booth machine. After a set the player is in the main window anyway. |
| Voice choice | `ELEVENLABS_VOICE_ID` in `app/.env`, no default | A default premade voice; a picker in Controls | One coach voice is chosen once for the video, the booth and the app, in the ElevenLabs account. It is a per-machine setting beside the key, and a picker would need the account's voice list in a page. |
| What `voice` in the brain config controls | Speaking only | Speaking and listening | The Controls toggle reads "Speaks between rounds and in the Coach tab". Holding to talk is a deliberate act and needs no second switch. |
| Who speaks between rounds | The main window, audio only | The overlay, with its card and a speaking indicator | The game screen belongs to the game, and the overlay is off by default. One speaker means one voice even when the overlay is on. |
| When a tip is spoken | As soon as its `coach` record arrives, always to the end | Only during the round break, stopping when the break ends | Waiting for the break delays the voice, and stopping at the next round cuts tips off mid-sentence. Keeping round tips short is the replay service's side of this. |
| Failed speech | Silent | A note on screen | The line it would have spoken is already on screen. |

## Open Questions & Future Decisions

### Deferred
1. Holding to talk while the game has focus (HLD open question), for a quick follow-up question between rounds.
2. OpenAI speech as the fallback when ElevenLabs is down (HLD, Voice). Until then a failure is text-only.

## References

- `../../high-level-design.md`: Voice component; secrets stay in the main process
- `../shell/shell-design.md`: settings sources, the bridge and its allow-list
- `../service-clients/service-clients-design.md`: the coach stream (`useCoachListener`)
- `../overlay/overlay-design.md`: the between-round card, silent
- `../main-window/coach/coach-design.md`: the Coach screen's input bar and conversation
- Paper file "Kumite — Tatami": Coach (speaking waveform)
- ElevenLabs API: `POST /v1/text-to-speech/{voice_id}/stream`, `GET /v1/voices/{voice_id}/settings`, `POST /v1/speech-to-text`
