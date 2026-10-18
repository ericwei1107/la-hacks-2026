# Voice specs

Design: `voice-design.md`

## Settings

- [ ] **VOICE-SET-001**: The main process shall read `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` once at startup, from the process environment first and then `app/.env`, treating an empty value as unset.
- [ ] **VOICE-SET-002**: If `ELEVENLABS_API_KEY` or `ELEVENLABS_VOICE_ID` is unset at startup, then the main process shall print a console warning naming each unset setting.
- [ ] **VOICE-SET-003**: The bridge shall pass neither the ElevenLabs key nor the voice id to any window.

## Speak

- [ ] **VOICE-SPEAK-001**: When a window calls `speak` with a text, the main process shall send `POST https://api.elevenlabs.io/v1/text-to-speech/<voice id>/stream?output_format=mp3_44100_128` with the `xi-api-key` header and the JSON body `{"text": <text>, "model_id": <model>, "voice_settings": <settings>}`, where the model is `eleven_flash_v2_5` until it has been refused.
- [ ] **VOICE-SPEAK-002**: While ElevenLabs streams a speak response with a 2xx status, the main process shall send each chunk to the asking window as it arrives, then an end marker, and resolve the speak call with success when the stream ends.
- [ ] **VOICE-SPEAK-008**: If ElevenLabs answers a speak request for `eleven_flash_v2_5` with 400, 403, 404 or 422, then the main process shall print a console warning, repeat the request with `eleven_turbo_v2_5`, and use `eleven_turbo_v2_5` for every later speak call.
- [ ] **VOICE-SPEAK-009**: The main process shall read the voice's stored settings once at startup from `GET https://api.elevenlabs.io/v1/voices/<voice id>/settings`, drop null values, and send them with `speed` set to 1.15 as `voice_settings`; if that read fails or takes longer than 3 seconds, it shall send `{"speed": 1.15}`.
- [ ] **VOICE-SPEAK-003**: If the key or the voice id is unset, then the speak call shall resolve with the failure reason `not_configured` without contacting ElevenLabs.
- [ ] **VOICE-SPEAK-004**: If ElevenLabs answers a speak request with a non-2xx status, then the speak call shall resolve with the failure reason `rejected` and that status.
- [ ] **VOICE-SPEAK-005**: If a speak request cannot be sent or its response is cut off, then the speak call shall resolve with the failure reason `network`.
- [ ] **VOICE-SPEAK-006**: If no response or chunk of a speak request has arrived for 6 seconds, then the main process shall abandon the request and resolve the speak call with the failure reason `timeout`.
- [ ] **VOICE-SPEAK-007**: If a speak call fails with `rejected`, `network` or `timeout`, then the main process shall print a console warning with the reason and, for `rejected`, the status.

## Transcribe

- [ ] **VOICE-HEAR-001**: When a window calls `transcribe` with a recording, the main process shall send `POST https://api.elevenlabs.io/v1/speech-to-text` with the `xi-api-key` header and a multipart body holding `model_id` `scribe_v2`, `language_code` `en` and the recording as `file`.
- [ ] **VOICE-HEAR-002**: When ElevenLabs answers a transcribe request with a 2xx status, the transcribe call shall resolve with the response's `text`, trimmed.
- [ ] **VOICE-HEAR-003**: If the key is unset, then the transcribe call shall resolve with the failure reason `not_configured` without contacting ElevenLabs.
- [ ] **VOICE-HEAR-004**: If a transcribe request is answered with a non-2xx status, cannot be sent, or takes longer than 10 seconds, then the transcribe call shall resolve with the failure reason `rejected` (with the status), `network` or `timeout`.

## Voice player

- [ ] **VOICE-PLAY-001**: When asked to speak a text, the voice player shall add the line to the end of its queue and start the line's speak call at once.
- [ ] **VOICE-PLAY-002**: When the line at the head of the queue has its first chunk, the voice player shall start playing it through Media Source Extensions and append each later chunk as it arrives.
- [ ] **VOICE-PLAY-008**: While a line is playing, the voice player shall not stop it for a new line, a round start, a state update, a screen change or a recording, and shall start the next queued line when it ends.
- [ ] **VOICE-PLAY-003**: The voice player shall report speaking from the moment its line starts playing until the line ends or fails to play.
- [ ] **VOICE-PLAY-004**: While the brain config's `voice` is not `true`, the voice player shall ignore requests to speak.
- [ ] **VOICE-PLAY-005**: When the brain config's `voice` stops being `true`, the voice player shall drop the queued lines that have not started and let the playing line finish.
- [ ] **VOICE-PLAY-007**: The voice player shall take a tag with each request to speak and report the tag of the line playing.
- [ ] **VOICE-PLAY-006**: If the window has no bridge, or a line's speak call fails before any chunk arrives, then the voice player shall skip that line.

## Between rounds

- [ ] **VOICE-ROUND-001**: When a `coach` record arrives on the brain's coach stream, the main window shall ask its voice player to speak that record's `text` at once.
- [ ] **VOICE-ROUND-003**: The main window shall show nothing on screen for the coach tip voice.

## Coach screen voice

- [ ] **VOICE-COACH-001**: When an answer arrives on the Coach screen, the screen shall ask the voice player to speak it.
- [ ] **VOICE-COACH-002**: When the player asks another question, switches sets or leaves the Coach screen while an answer is playing or queued, the Coach screen shall leave it playing or queued.
- [ ] **VOICE-COACH-003**: While the voice player speaks an answer, the Coach screen shall show a 64 × 20 waveform and "Speaking" at 14 px bold in `--color-primary` after that answer's "Coach" label.

## Hold to talk

- [ ] **VOICE-TALK-001**: While the player holds the "Hold to talk" button, or holds the push-to-talk key while the main window has focus, the Coach screen is showing and focus is not in the text field, the main window shall record the microphone and show "Listening…" on the button.
- [ ] **VOICE-TALK-002**: The main window shall ignore key repeats of the push-to-talk key.
- [ ] **VOICE-TALK-003**: When the player releases after a recording of 300 ms or longer, the main window shall transcribe it, showing "Transcribing…" on the button, and send the text as a question as if typed.
- [ ] **VOICE-TALK-004**: When the player releases after a recording shorter than 300 ms, the main window shall discard it without a transcribe call.
- [ ] **VOICE-TALK-005**: When a recording reaches 30 seconds, the main window shall stop it and transcribe it as if released.
- [ ] **VOICE-TALK-006**: When a transcript arrives after the player has switched sets or left the Coach screen, the main window shall drop it.
- [ ] **VOICE-TALK-007**: When a transcript is empty, the Coach screen shall show "Didn't catch that. Hold the key and try again." in muted text under the input bar.
- [ ] **VOICE-TALK-008**: If the microphone or the transcribe call fails, then the Coach screen shall show "Couldn't hear you. <reason>" in muted text under the input bar.
- [ ] **VOICE-TALK-009**: The main process shall grant microphone permission requests from the app's own pages, refuse every other media permission request, and on macOS ask the system for microphone access the first time a recording starts.
- [ ] **VOICE-TALK-010**: While the Coach screen's text field is disabled, or the window has no bridge, the Coach screen shall draw the "Hold to talk" button disabled and ignore the push-to-talk key.
- [ ] **VOICE-TALK-011**: While a recording is being transcribed, the main window shall ignore new presses of the "Hold to talk" button and the push-to-talk key.
- [ ] **VOICE-TALK-012**: When the player starts another recording or sends a typed question, the Coach screen shall clear the muted line under the input bar.
- [ ] **VOICE-TALK-013**: When a recording starts, the main window shall leave its voice player playing.

## Talk key from the game

- [ ] **VOICE-TALK-014**: The main process shall register `KUMITE_TALK_KEY` (the process environment first, then `app/.env`; `F8` when unset) as a global shortcut unless its value is `0` or `off`, and send the main window a talk message each time it is pressed.
- [ ] **VOICE-TALK-015**: If the talk key cannot be registered or is not a valid accelerator, then the main process shall print a console warning naming the key and the bridge shall report no talk key.
- [ ] **VOICE-TALK-016**: While live state is arriving and the last `round_end` seen for that set did not carry `match_over` true, the main window shall ignore talk messages.
- [ ] **VOICE-TALK-017**: When a talk message arrives outside a match, the main window shall open the Coach screen for the selected set and start a recording, or stop and transcribe the recording already in progress.
- [ ] **VOICE-TALK-018**: While the bridge reports a talk key, the Coach screen shall show "After a match, press <key> from the game to talk; press it again to send." in muted text under the input bar.

## Implemented in

| Spec IDs | Entry point |
|---|---|
| VOICE-SET-001 – VOICE-SET-003, VOICE-SPEAK-001 – VOICE-SPEAK-009 | `src/main/voice.ts` (`readVoiceSettings`, `handleVoice`); chunk channel in `src/preload/index.ts` (`speak`) |
| VOICE-PLAY-001 – VOICE-PLAY-008 | `src/renderer/src/voice.ts` (`useVoice`) |
| VOICE-COACH-001 – VOICE-COACH-003 | `src/renderer/src/main-window/screens/Coach.tsx` (`Conversation`, `CoachAnswer`) |
| VOICE-ROUND-001, VOICE-ROUND-003 | `src/renderer/src/voice.ts` (`useCoachRecordVoice`), called by `src/renderer/src/main-window/MainWindow.tsx` (`CoachRecordVoice`) |
| VOICE-HEAR-001 – VOICE-HEAR-004, VOICE-TALK-009 | `src/main/voice.ts` (`handleVoice`, `handleMicrophone`) |
| VOICE-TALK-001 – VOICE-TALK-008, VOICE-TALK-010 – VOICE-TALK-013 | `src/renderer/src/voice.ts` (`useHoldToTalk`), used by `src/renderer/src/main-window/screens/Coach.tsx` (`Conversation`) |
| VOICE-TALK-014, VOICE-TALK-015 | `src/main/index.ts` (the `app.whenReady` handler) with `src/main/services.ts` (`talkKey`) |
| VOICE-TALK-016, VOICE-TALK-017 | `src/renderer/src/main-window/GlobalTalk.tsx` (`GlobalTalk`), consumed by `src/renderer/src/main-window/screens/Coach.tsx` (`Conversation`) through `src/renderer/src/main-window/talkRequests.ts` |
| VOICE-TALK-018 | `src/renderer/src/main-window/screens/Coach.tsx` (`Conversation`) |
