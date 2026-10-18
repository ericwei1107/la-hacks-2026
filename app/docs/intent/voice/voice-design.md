---
parent: high-level-design
prefix: VOICE
---

# Voice

## Context and Design Philosophy

The coach speaks and listens through ElevenLabs. Voice never runs during live play: a voice mid-round distracts, and a spoken answer would land after the moment has passed. So the coach speaks in two places, both outside a round: between rounds of a set, from the main window with nothing on screen, and in the Coach screen after a set, where the player can also ask a question by holding to talk.

The main process makes every ElevenLabs call, because it holds the key (HLD, secrets stay in the main process). The windows play and record audio, because only a page has the audio and microphone APIs. The two meet over two bridge calls: speak, which turns text into a clip, and transcribe, which turns a recording into text.

Voice is an addition, never a dependency. Every line the coach speaks is also on screen, and every voice failure leaves the app as it is without voice: the text still shows, and a typed question still works.

## Settings

| Setting | Read from | Needed for |
|---|---|---|
| `ELEVENLABS_API_KEY` | The process environment, then `app/.env` | Speaking and transcribing |
| `ELEVENLABS_VOICE_ID` | The process environment, then `app/.env` | Speaking |

The main process reads both once at start, from the same sources and in the same order as the service addresses (shell). An empty value counts as unset. Neither value ever crosses the bridge. The coach's voice is chosen in the ElevenLabs account and set once per machine; there is no default voice.

The brain config's `voice` flag turns speaking on and off for both windows; turning it off stops a line already playing. It does not affect listening: holding to talk is the player's own action.

When a setting is unset at start, the main process prints which one to its console, so a silent coach at the booth has a visible cause. It prints each failed ElevenLabs call there too.

## Main process: the ElevenLabs calls

**Speak.** `POST https://api.elevenlabs.io/v1/text-to-speech/<voice id>?output_format=mp3_44100_128` with the `xi-api-key` header and the body `{ "text", "model_id": "eleven_flash_v2_5" }`. The whole MP3 clip comes back to the asking window as bytes. The call gives up after 6 seconds.

**Transcribe.** `POST https://api.elevenlabs.io/v1/speech-to-text` with the `xi-api-key` header and a multipart body: `model_id` `scribe_v2`, `language_code` `en`, and the recording as `file`. The response's `text`, trimmed, comes back to the asking window. The call gives up after 10 seconds.

Both calls answer with a result rather than throwing: the clip or the text, or a failure with one of these reasons.

| Reason | When | Shown to the player as |
|---|---|---|
| `not_configured` | A setting the call needs is unset; ElevenLabs is not contacted | "Voice isn't set up on this machine." |
| `rejected` | ElevenLabs answered with a non-2xx status | "ElevenLabs refused the request (<status>)." |
| `network` | The request could not be made or was cut off | "Can't reach ElevenLabs." |
| `timeout` | No answer within the call's limit | "ElevenLabs took too long." |

A failed speak is silent: the line is already on screen. A failed transcribe tells the player why, because they are waiting for their question to appear.

## The bridge

The bridge gains two calls on `window.kumite`, carried over `ipcRenderer.invoke`:

- `speak(text)` → the MP3 bytes, or a failure reason.
- `transcribe(recording, mimeType)` → the text, or a failure reason.

The shell owns the bridge and its allow-list; this design owns what the two calls do. In a plain browser there is no bridge, so voice is unavailable there and the app runs text-only.

## Speaking: the voice player

Each window has one voice player. It plays one clip at a time:

- Asked to speak, it stops whatever it is playing or waiting for, asks the bridge for the clip, and plays it when it arrives.
- Asked to stop, it ends playback and throws away any clip still on its way, so a slow clip can never start after the moment it belonged to.
- It reports whether it is speaking, and whose clip it is: each request carries a tag naming its caller (the round tip, or one Coach screen answer). A screen shows its speaking indicator only for its own clip, and a screen that goes away stops only its own clips, so leaving the Coach screen never cuts off a round tip.
- It ignores requests to speak while the brain config's `voice` is not `true`, and when the bridge is missing or the speak call fails it plays nothing.

Chromium blocks sound from a page the user has not interacted with, and between rounds the player's hands are on the game, perhaps before anyone has clicked the main window. So both windows are created with autoplay allowed without a user gesture, and the main window keeps running at full speed while the game covers it (shell).

**Between rounds (main window).** The main window follows the round break (HLD) through the service clients. When the live set's `coach` record for the break's round is available during the break, the main window speaks it once per break. When the break ends, it stops the voice, so the coach never talks into the next round. Nothing is shown: the game screen belongs to the game, and the main window is behind it. The overlay, when turned on, shows its card silently, so there is only ever one voice.

**Coach screen.** When an answer arrives, the screen speaks it. Asking another question, starting to hold to talk, switching sets or leaving the screen stops it. While an answer is being spoken, its "Coach" label is followed by a 64 × 20 indigo waveform and "Speaking" at 14 px bold in indigo.

## Listening: hold to talk (main window)

The player asks the coach by voice on the Coach screen, in either of two ways:

- **Hold the "Hold to talk" button.** Recording starts on press and stops on release, or when the pointer leaves the button or is cancelled.
- **Hold the push-to-talk key** while the main window has focus, the Coach screen is showing and focus is not in the text field (so the key can still be typed). Key repeats are ignored.

While recording, the button reads "Listening…". On release, a recording shorter than 300 ms is thrown away without a request (a tap, not a question). A longer one is transcribed while the button reads "Transcribing…", and the text is sent as a question exactly as if it had been typed. Recording stops by itself after 30 seconds and is transcribed as if released.

Starting to record stops the coach's voice. A transcript that arrives after the player has switched sets or left the Coach screen is dropped, so a question never lands in a conversation it was not asked in. The recording is the microphone's audio in the browser's default `MediaRecorder` format (WebM with Opus in Electron), which Scribe accepts.

When the transcript is empty, a muted line under the input bar reads "Didn't catch that. Hold the key and try again." When the microphone or the call fails, the line reads "Couldn't hear you. <reason>", with "Microphone access is off. Allow it in System Settings → Privacy & Security → Microphone." for a refused microphone. The line clears on the next attempt or the next typed question.

Hold to talk is unavailable, and the button drawn disabled, under the same conditions as the text field (replay service offline, answer pending), and in a plain browser. While a recording is being transcribed, new presses are ignored.

**Microphone permission.** The main process grants microphone requests from the app's own pages and refuses every other media request. On macOS it asks the system for microphone access the first time a recording starts.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| How a clip reaches the window | The whole MP3 over one bridge call | Streaming chunks over IPC into Media Source Extensions; a privileged custom protocol the audio element streams from | Flash v2.5 answers in about 75 ms of model time, so a 40-word clip returns in about a second, well inside the 8 to 10 second round-end screen. One call and a blob URL are far less code than either streaming path. Streaming is the fallback if the first sound takes longer than 1.5 seconds on the booth network. |
| Speech model | `eleven_flash_v2_5` | `eleven_v4_turbo`; `eleven_multilingual_v2` | Lowest listed latency; the coach speaks English, and the round-end window is short. |
| Transcription | One `scribe_v2` request on release | `scribe_v2_realtime` streaming while the key is held | Questions are a sentence or two; one request after release is one call with no socket to manage. |
| Where hold to talk works | The main window, while it has focus | A global key while the game has focus | Electron's global shortcuts report presses but not releases, so holding a key over the game needs a native keyboard hook, a compiled dependency on the booth machine. After a set the player is in the main window anyway. |
| Voice choice | `ELEVENLABS_VOICE_ID` in `app/.env`, no default | A default premade voice; a picker in Controls | One coach voice is chosen once for the video, the booth and the app, in the ElevenLabs account. It is a per-machine setting beside the key, and a picker would need the account's voice list in a page. |
| What `voice` in the brain config controls | Speaking only | Speaking and listening | The Controls toggle reads "Speaks between rounds and in the Coach tab". Holding to talk is a deliberate act and needs no second switch. |
| Who speaks between rounds | The main window, audio only | The overlay, with its card and a speaking indicator | The game screen belongs to the game, and the overlay is off by default. One speaker means one voice even when the overlay is on. |
| Voice when the round break ends | Stops | Finishes the sentence | Voice never runs during live play. The break covers the whole round-end screen, so a stop only cuts a line that ran long; keeping round tips short is the replay service's side of this. |
| Failed speech | Silent | A note on screen | The line it would have spoken is already on screen. |

## Open Questions & Future Decisions

### Deferred
1. Holding to talk while the game has focus (HLD open question), for a quick follow-up question between rounds.
2. OpenAI speech as the fallback when ElevenLabs is down (HLD, Voice). Until then a failure is text-only.

## References

- `../../high-level-design.md`: Voice component; secrets stay in the main process
- `../shell/shell-design.md`: settings sources, the bridge and its allow-list
- `../service-clients/service-clients-design.md`: the round break (`useRoundBreak`)
- `../overlay/overlay-design.md`: the between-round card, silent
- `../main-window/coach/coach-design.md`: the Coach screen's input bar and conversation
- Paper file "Kumite — Tatami": Coach (speaking waveform)
- ElevenLabs API: `POST /v1/text-to-speech/{voice_id}`, `POST /v1/speech-to-text`
