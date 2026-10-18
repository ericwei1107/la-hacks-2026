# Voice specs

Design: `voice-design.md`

## Settings

- [ ] **VOICE-SET-001**: The main process shall read `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` once at startup, from the process environment first and then `app/.env`, treating an empty value as unset.
- [ ] **VOICE-SET-002**: If `ELEVENLABS_API_KEY` or `ELEVENLABS_VOICE_ID` is unset at startup, then the main process shall print a console warning naming each unset setting.
- [ ] **VOICE-SET-003**: The bridge shall pass neither the ElevenLabs key nor the voice id to any window.

## Speak

- [ ] **VOICE-SPEAK-001**: When a window calls `speak` with a text, the main process shall send `POST https://api.elevenlabs.io/v1/text-to-speech/<voice id>?output_format=mp3_44100_128` with the `xi-api-key` header and the JSON body `{"text": <text>, "model_id": "eleven_flash_v2_5"}`.
- [ ] **VOICE-SPEAK-002**: When ElevenLabs answers a speak request with a 2xx status, the speak call shall resolve with the response body's bytes.
- [ ] **VOICE-SPEAK-003**: If the key or the voice id is unset, then the speak call shall resolve with the failure reason `not_configured` without contacting ElevenLabs.
- [ ] **VOICE-SPEAK-004**: If ElevenLabs answers a speak request with a non-2xx status, then the speak call shall resolve with the failure reason `rejected` and that status.
- [ ] **VOICE-SPEAK-005**: If a speak request cannot be sent or its response is cut off, then the speak call shall resolve with the failure reason `network`.
- [ ] **VOICE-SPEAK-006**: If ElevenLabs has not finished answering a speak request within 6 seconds, then the main process shall abandon the request and resolve the speak call with the failure reason `timeout`.
- [ ] **VOICE-SPEAK-007**: If a speak call fails with `rejected`, `network` or `timeout`, then the main process shall print a console warning with the reason and, for `rejected`, the status.

## Transcribe

- [D] **VOICE-HEAR-001**: When a window calls `transcribe` with a recording, the main process shall send `POST https://api.elevenlabs.io/v1/speech-to-text` with the `xi-api-key` header and a multipart body holding `model_id` `scribe_v2`, `language_code` `en` and the recording as `file`.
- [D] **VOICE-HEAR-002**: When ElevenLabs answers a transcribe request with a 2xx status, the transcribe call shall resolve with the response's `text`, trimmed.
- [D] **VOICE-HEAR-003**: If the key is unset, then the transcribe call shall resolve with the failure reason `not_configured` without contacting ElevenLabs.
- [D] **VOICE-HEAR-004**: If a transcribe request is answered with a non-2xx status, cannot be sent, or takes longer than 10 seconds, then the transcribe call shall resolve with the failure reason `rejected` (with the status), `network` or `timeout`.

## Voice player

- [ ] **VOICE-PLAY-001**: When asked to speak a text, the voice player shall stop the clip it is playing, discard any clip still on its way, and play the new text's clip when the speak call returns it.
- [ ] **VOICE-PLAY-002**: When asked to stop, the voice player shall end playback and discard any clip still on its way.
- [ ] **VOICE-PLAY-003**: The voice player shall report speaking from the moment its clip starts playing until the clip ends, is stopped, or fails to play.
- [ ] **VOICE-PLAY-004**: While the brain config's `voice` is not `true`, the voice player shall ignore requests to speak.
- [ ] **VOICE-PLAY-005**: When the brain config's `voice` stops being `true`, the voice player shall stop.
- [ ] **VOICE-PLAY-006**: If the window has no bridge or the speak call fails, then the voice player shall play nothing.

## Between rounds

- [ ] **VOICE-ROUND-001**: When a round break is open in the main window and a `coach` record for the break's set and round is available, the main window shall ask its voice player to speak that record's `text`, once per round break.
- [ ] **VOICE-ROUND-002**: When a round break in the main window ends, the main window shall stop its voice player.
- [ ] **VOICE-ROUND-003**: The main window shall show nothing on screen for the between-round voice.

## Coach screen voice

- [D] **VOICE-COACH-001**: When an answer arrives on the Coach screen, the screen shall ask the voice player to speak it.
- [D] **VOICE-COACH-002**: When the player asks another question, starts to hold to talk, switches sets or leaves the Coach screen, the screen shall stop the voice player.
- [D] **VOICE-COACH-003**: While the voice player speaks an answer, the Coach screen shall show a 64 × 20 waveform and "Speaking" at 14 px bold in `--color-primary` after that answer's "Coach" label.

## Hold to talk

- [D] **VOICE-TALK-001**: While the player holds the "Hold to talk" button, or holds the push-to-talk key while the main window has focus, the Coach screen is showing and focus is not in the text field, the main window shall record the microphone and show "Listening…" on the button.
- [D] **VOICE-TALK-002**: The main window shall ignore key repeats of the push-to-talk key.
- [D] **VOICE-TALK-003**: When the player releases after a recording of 300 ms or longer, the main window shall transcribe it, showing "Transcribing…" on the button, and send the text as a question as if typed.
- [D] **VOICE-TALK-004**: When the player releases after a recording shorter than 300 ms, the main window shall discard it without a transcribe call.
- [D] **VOICE-TALK-005**: When a recording reaches 30 seconds, the main window shall stop it and transcribe it as if released.
- [D] **VOICE-TALK-006**: When a transcript arrives after the player has switched sets or left the Coach screen, the main window shall drop it.
- [D] **VOICE-TALK-007**: When a transcript is empty, the Coach screen shall show "Didn't catch that. Hold the key and try again." in muted text under the input bar.
- [D] **VOICE-TALK-008**: If the microphone or the transcribe call fails, then the Coach screen shall show "Couldn't hear you. <reason>" in muted text under the input bar.
- [D] **VOICE-TALK-009**: The main process shall grant microphone permission requests from the app's own pages, refuse every other media permission request, and on macOS ask the system for microphone access the first time a recording starts.

## Implemented in

| Spec IDs | Entry point |
|---|---|
| VOICE-SET-001 – VOICE-SET-003, VOICE-SPEAK-001 – VOICE-SPEAK-007 | `src/main/voice.ts` (`readVoiceSettings`, `handleVoice`) |
| VOICE-PLAY-001 – VOICE-PLAY-006 | `src/renderer/src/voice.ts` (`useVoice`) |
| VOICE-ROUND-001 – VOICE-ROUND-003 | `src/renderer/src/voice.ts` (`useBetweenRoundVoice`), called by `src/renderer/src/main-window/MainWindow.tsx` |
