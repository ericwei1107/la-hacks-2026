---
parent: main-window
prefix: MAIN-COACH
---

# Coach screen

## Context and Design Philosophy

The Coach screen is a conversation with the coach about the selected set. Paper: the Coach artboard. The player's questions sit on the right in indigo bubbles; the coach's answers sit on the left as plain text under a "Coach" label, with citation chips that jump to the moments it used. The input bar, framed by an indigo rule, offers hold-to-talk and typing.

## Conversation

The conversation belongs to the selected set and lasts while the app runs: switching sets switches conversations, and switching back restores the earlier one. Each question is sent to the replay service's `/coach/chat` with the set id, the player's name (from the brain config, or the set's player when the config is unavailable), the message, and the history so far as `{role, text}` entries with roles `user` and `coach`.

- While an answer is pending, a "Coach" label with "Thinking…" stands where the answer will appear, and the input is disabled.
- **Reading an answer.** The replay service returns one block of text, so the screen splits it along the sentence forms the coach writes:
  - A practice priority, "Start with <priority>." or "Next, work on <priority>.", becomes a card on the surface tone: "First" or "Next" in indigo, the priority as its title, then what was observed, then the drill (the sentence starting "In Practice,") after a bold "Drill".
  - A moment, "Round <r>, frame <f>: …", becomes a row with "Round <r>, frame <f>" in mono at the left and the description beside it.
  - Any other text stays a paragraph, in place. An answer with none of these forms reads as one paragraph, as before.
  - The answer's citation chips stay together under it: the reply does not say which priority or moment each citation belongs to.
  - The whole answer is still spoken as one text.
- A citation chip reads "Round <r>, frame <f>" with a play mark. Activating it opens Replay analysis on this set, focused at that round and frame.
- If the request fails, the pending answer is replaced by a muted line, "Couldn't reach the coach. <reason>", and the question stays in the history so the player can ask again.
- An empty conversation shows a prompt in muted text: "Ask about this set. Try: Why did I lose round 2?"

## Input bar

- **Hold to talk**, with the push-to-talk key as a key cap. Holding the button, or the key, records a spoken question; on release it is transcribed and sent like a typed one. The button reads "Listening…" while recording and "Transcribing…" after, and a muted line under the input bar explains a question that could not be heard. The voice design owns this behavior.
- **Type a question:** a text field, "Or type a question about this set", with a send arrow. Enter or the arrow sends; an empty field sends nothing.
- **Coach voice:** a toggle bound to the brain config's `voice`, saved when changed.

When an answer arrives it is spoken, and while it plays its "Coach" label is followed by Paper's "Speaking" waveform (voice design). It plays to the end: asking again, switching sets or leaving the screen does not stop it, and a later answer waits its turn.

## States

- **No sets:** the empty state "No set to talk about yet." / "Play a set against Kumite, then ask the coach about it."
- **Offline:** the offline banner for the replay service; the field and send button are disabled.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Conversation lifetime | Per set, for the app's run | Persisted to disk; cleared on every visit | The coach answers about one set; keeping each set's thread while the app runs supports going back and forth without storing transcripts. |
| Splitting answers | Along the coach's fixed sentence forms ("Start with", "Next, work on", "In Practice,", "Round <r>, frame <f>:") | A structured reply from the replay service | `/coach/chat` returns `{text, citations}` and the contracts are frozen. The coach writes priorities and moments in fixed forms, so splitting on them is presentation only, and text in any other form still reads as a paragraph. A structured reply would need all four owners to agree. |
| History roles | `user` and `coach` | `user` and `assistant` | `contracts/api.md` names no roles; these match the screen's own words until the replay service says otherwise (service-clients, deferred question). |

## References

- Paper file "Kumite — Tatami": Coach
- `../../service-clients/service-clients-design.md` (chat call)
- `../../voice/voice-design.md` (hold to talk)
