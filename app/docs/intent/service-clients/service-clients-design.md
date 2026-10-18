---
parent: high-level-design
prefix: CLIENT
---

# Service clients

## Context and Design Philosophy

Both app windows talk to the brain, replay analysis and analytics services directly (HLD, Key Design Decisions). This component is the only code in a window that knows service addresses, paths, request and response shapes, and connection state. A screen asks it for data and gets back contract-typed values plus a state it can render: loading, ready, not analyzed, offline, timed out, or failed. Because offline handling lives here, a stopped service looks the same on every screen and the rest of the app keeps working (HLD Success Metrics).

Principles:

- **The contract is the type.** Every value that comes from a service is typed from `contracts/`; screens never handle untyped JSON.
- **Read tolerantly.** Unknown fields and unknown record types are ignored, dropped `/ws/state` frames are expected, and a truncated last recording line is expected (`contracts/api.md`, `contracts/recording.md`).
- **Pass through, don't derive.** The clients return what the services return. A number a screen needs and no endpoint provides is a request to the service that owns the data (HLD tenet *Ask the service, don't compute*), not a computation added here.
- **One set per window.** Each window runs its own clients, streams and status. The two windows can briefly disagree; the HLD accepts that cost in exchange for not routing data through the main process.

## Addresses

The clients read `window.kumite.services` (shell) once, when the module loads. When the bridge is absent, as in the renderer dev server opened in a plain browser, they use the shell's defaults, `http://localhost:8765`, `:8766` and `:8767`, each with source `default`. A plain browser can then build and hot-reload screens against the mock services.

WebSocket URLs come from the brain address by swapping the scheme (`http:` to `ws:`, `https:` to `wss:`) and appending the stream path.

## Contract types

One module holds a TypeScript type for every schema file in `contracts/` (gamestate, event, session, round_summary, report, metrics, profile, gameplan, config). Type names follow the schema titles, except that the event type is `GameEvent`, so it does not shadow the DOM's `Event`. It also types the shapes `contracts/api.md` defines inline without a schema file: the health reply, the coach message on `/ws/coach`, the `/coach/chat` request and reply, and the `/stats` and `/trends` replies.

Types are written by hand from the schemas, field for field. A property outside a schema's `required` list is optional in the type, a string `enum` is a union of literals, and a `["number", "null"]` type is `number | null`. Contracts change only when all four owners agree (`contracts/api.md`), and the type module is updated as part of absorbing such a change.

Responses are not validated against the schemas at run time. A client checks only that a body is JSON of the expected top-level kind, object or array. Anything else is a bad-response failure.

## HTTP calls

`getInsights` reads the analytics service's insights view, which is not yet a shared contract: its type, `InsightsV1`, mirrors Eric's draft (`analytics/insights_v1.schema.json` on the insights branch) rather than a file in `contracts/`, and only the focus card calls it, behind the `KUMITE_INSIGHTS` switch (focus design).

| Call | Service | Request | Resolves with | Timeout |
|---|---|---|---|---|
| `listSessions()` | brain | `GET /sessions` | `SessionMeta[]`, newest first as served | 10 s |
| `getSession(id)` | brain | `GET /sessions/{id}` | `SessionMeta` | 10 s |
| `getRecording(id, { states })` | brain | `GET /sessions/{id}/recording` | `Recording` (see Recording reader) | 60 s |
| `getProfiles(player)` | brain | `GET /profiles/{player}` | `Profile[]` | 10 s |
| `getConfig()` | brain | `GET /config` | `Config` | 10 s |
| `postConfig(partial)` | brain | `POST /config` | `Config`, the merged result | 10 s |
| `getReport(id)` | replay | `GET /reports/{id}` | `Report`, or `null` on 404 (not analyzed yet) | 10 s |
| `analyze(id)` | replay | `POST /analyze/{id}` | `Report` | 5 min |
| `chat(request)` | replay | `POST /coach/chat` | `ChatReply` (`text`, `citations`) | 60 s |
| `getStats(id)` | analytics | `GET /stats/{id}` | `SessionStats` | 10 s |
| `getTrends(player, character, stat?)` | analytics | `GET /trends/{player}/{character}` with optional `?stat=` | `Trends` | 10 s |
| `getLearning(id)` | analytics | `GET /learning/{id}` | `LearningMetrics` | 10 s |
| `getInsights(id)` | analytics | `GET /insights/{id}?limit=3` | `InsightsV1` | 10 s |
| `health(service)` | each | `GET /health` | `Health` | 2 s |

Path segments and the `stat` query value are percent-encoded. Request bodies are JSON with `Content-Type: application/json`.

`postConfig` sends only the fields the caller passes, as the contract allows a partial body, and it changes nothing in the app until the brain answers with the merged config.

`analyze` calls for the same session share one request: a call made while another for that session is in flight returns the pending result instead of starting a second analysis.

### Failures

Every call resolves with its typed value or rejects with a `ServiceError` that names the service, the call, and one kind:

| Kind | When |
|---|---|
| `offline` | No HTTP response at all: connection refused, unknown host, or any other network failure |
| `timeout` | No complete response within the call's timeout |
| `not_found` | HTTP 404, except on `getReport`, where 404 resolves `null` |
| `http` | Any other non-2xx status. Carries the status code and the server's message: the `detail` field of a JSON error body when present, written as JSON text when it is not a string (FastAPI validation errors are arrays), otherwise the body. Either one is cut to 200 characters |
| `bad_response` | A 2xx reply whose body is not JSON or not the expected top-level kind |

A failure of kind `offline` marks its service offline. A `timeout` leaves the status as it was: the service may be reachable but slow, which a screen shows differently from a stopped service. Every other kind means an HTTP response arrived, which marks the service online (see Service status).

## Recording reader

`getRecording` reads the NDJSON body as a stream and parses it one line at a time, so the whole file is never held as one string.

Line rules, from `contracts/recording.md`:

- A blank line is skipped.
- A line that does not parse as a JSON object is skipped and counted. A truncated last line, from a recording still being written, is the expected case.
- A record whose `t` is not one of `state`, `event`, `tactical`, `plan` or `round_summary` is skipped.
- Fields outside the type are left on the record untouched.

The result holds the session id, one array per record type in file order (`events`, `roundSummaries`, `plans`, `tactical`), and the count of skipped lines. `state` records are kept only when the caller passes `states: true`. A recording carries about 60 of them per second at roughly 2 KB each, so a three-round set reaches tens of megabytes, while the sessions timeline and clip timestamps need only events and round summaries.

## Live streams

The brain has two WebSocket streams: **state** (`/ws/state`) and **coach** (`/ws/coach`).

**Lifecycle.** A stream's socket opens when the first subscriber in a window subscribes. From then on it stays open for the window's lifetime, reconnecting as needed.

**Reconnecting.** When a socket closes or fails to open, the stream tries again after 0.5 s, doubling the wait up to 5 s. A successful open resets the wait to 0.5 s. A stream keeps trying for as long as its window lives. An attempt that has not opened within 3 s is abandoned and counts as a failed open: the live brain runs only during a match, on a laptop whose firewall drops connections to the closed port instead of refusing them, and such an attempt would otherwise hang for over a minute. With the timeout, the app picks up a brain that starts within about 8 s.

**Stream status.** Each stream is in one of three states:

- `connecting`: no socket has opened yet.
- `open`
- `reconnecting`: a socket was open and has closed, and the stream is retrying.

**Messages.** Each text frame is parsed as JSON. A frame that is not a JSON object with a string `t` is ignored. Recognized records are delivered as follows:

| Stream | `t` | Delivered as |
|---|---|---|
| state | `state` | Replaces the latest-state slot; state subscribers are notified on every frame |
| state | `event` | Passed to every event listener, in arrival order; not kept |
| state | `plan` | Replaces the latest-plan slot. The brain does not send these yet; the slot stays empty until it does |
| coach | `coach` | Replaces the latest-coach slot and is passed to every coach listener |
| coach | `round_summary` | Replaces the latest-summary slot and is passed to every summary listener |
| either | anything else | Ignored |

**Slots.** A slot holds the most recent record of its kind and the wall-clock time the window received it, or nothing before the first one arrives. A component that mounts late, such as the between-round card appearing after the tip arrived, reads the slot. Slots are not cleared on reconnect or when a new session starts. Each record carries `session_id` and `round`, and the receive time shows freshness, so the consumer decides whether a slot still applies.

**Dropped and missed records.** Nothing in the clients depends on consecutive state frames; the latest-state slot is the only state they keep. Events sent while a socket is down are not recovered, and delivery resumes with the next event after reconnecting. The recording is the complete history.

## Live set and round break

The live set, a live round and the round break are defined in the HLD; the clients track them once, in one hook, so the main window's between-round voice and the overlay's card agree on when a break starts and ends.

`useRoundBreak` reads the latest-state slot and listens for events. It returns the latest state, the live set, whether a round is live, and the open round break, if any. A round break records its set, its round, when its `round_end` event reached the window, and whether that event's `detail.match_over` is `true`.

- A `round_end` event for the live set opens a round break for the event's round, replacing any break already open.
- A `round_start` event for the break's set ends it, whatever the event's round, so a replayed or reset round still ends the break.
- A `state` record for a later round of the break's set ends it, in case the `round_start` event was missed while a socket was down.
- A `state` record for another set ends it.
- The round stopping being live ends it. This is how the break after a set's final round ends: the brain stops the state stream once the game leaves the match.

The hook re-checks liveness every 250 ms. Each window that calls it keeps its own break; the windows open separate sockets, so their breaks can differ by the time a record takes to reach each.

## Service status

Each window tracks one status per service. It holds:

- `unknown` (not checked yet), `online` or `offline`;
- the address with its source and any warning, as the shell resolved it;
- the last-checked time: when a health reply or a call outcome last set the status;
- the `service` name and `version` from the last successful `/health` reply.

Status changes come from two places:

- **Health polling.** `GET /health` on all three services as soon as the window starts, then every 5 s. A 2xx reply with `ok: true` means `online`. Anything else, timeout included, means `offline`.
- **Call outcomes.** A call that fails with `offline` sets its service `offline` immediately. A call other than `/health` that gets any HTTP response, error statuses included, sets its service `online`. A call that fails with `timeout` leaves the status unchanged.

The brain's stream statuses are separate from its service status: the brain can answer HTTP while a stream is reconnecting.

## React bindings

Screens use hooks built on TanStack Query. A provider component wraps each window's root, owns that window's query client, and starts health polling.

- **Query hooks**, one per read call: `useSessions`, `useSession`, `useRecording`, `useProfiles`, `useConfig`, `useReport`, `useStats`, `useTrends`, `useLearning`. Each returns the query's state. When there is an error, it is a `ServiceError`, so a screen picks the offline, timed-out or failure state from its kind.
- **Mutation hooks:**
  - `usePostConfig` writes the brain's merged config into the config query.
  - `useAnalyze` writes the returned report into that session's report query.
  - `useChat` writes nothing into the query cache; the coach screen owns the conversation history it sends.
- **Query keys** start with the service name. When a service goes from `offline` to `online`, the provider refetches that service's queries and no others.
- **Connectivity.** Calls run whatever network connectivity the browser reports. The services are on localhost or a direct link, which a machine with no internet route still reaches.
- **No automatic retries.** A query that fails `offline` refetches when its service comes back. Any other failure stays failed until the screen asks again.
- **Config freshness.** `useConfig` refetches every 5 s while mounted, so the overlay HUD follows changes made from the main window, or from another machine during integration.
- **Stream hooks:**
  - `useLiveState`, `useLatestPlan`, `useLatestCoach` and `useLatestSummary` read the slots.
  - `useEventListener`, `useCoachListener` and `useSummaryListener` register a listener for the component's lifetime.
  - `useStreamStatus` reads a stream's status and counts as a subscriber, so a status view opens the stream it reports on.
  - `useRoundBreak` reads the live set, whether a round is live, and the open round break.
- **`useServiceStatus`** reads a service's status.

## Module layout

All of it lives under `src/renderer/src/services/`, shared by every window's renderer entry: the contract types, the address reader, the HTTP core and errors, one module per service, the recording reader, the streams, the status tracker, and the hooks with their provider.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Contract types | Written by hand from the schemas | Generated with `json-schema-to-typescript` | Generation cannot cover the shapes `api.md` defines inline, emits the schemas' descriptions as comments the code style forbids, and adds a build step. The contracts are frozen, so hand-written types have little to drift from. |
| Run-time response checking | Top-level kind only | Full JSON Schema validation with Ajv in each window | Ajv compiles validators with `new Function`, which needs `unsafe-eval` in the page. It also needs the dev server to serve files from outside `app/`, and it turns one malformed optional field into a failed screen during a live demo. Each service validates its own outputs against the schemas (root `CLAUDE.md`). |
| Query and cache layer | TanStack Query | Hand-written hooks over a small cache | Caching, request de-duplication, focus refetching, mutation state and invalidation by key prefix are the parts that are easy to get subtly wrong. TanStack Query is widely known, so screen code reads as familiar to any teammate or agent. |
| Timeouts and service status | `timeout` is its own kind and leaves status alone; only a network failure marks a service offline | Treating a timeout as offline | A slow analysis or chat reply over venue Wi-Fi would otherwise flip every screen that uses that service to offline until the next poll. |
| Automatic retries | None. Offline queries refetch when their service returns | The library default of three retries with backoff | Retries hold a screen in loading for tens of seconds and hide the offline state every screen must show (HLD G8). Recovery is driven by service status instead. |
| Config freshness across windows | `useConfig` refetches every 5 s | The shell relays a config-changed signal between windows; a brain push the contract does not define | Polling also catches changes made from another machine during integration and needs no bridge channel. |
| How state subscribers are notified | On every received frame | Coalescing to animation frames | At 60 frames a second, React handles per-frame updates of a small HUD. Coalescing adds code and a second idea of "latest" for no visible gain. |
| Socket lifetime | Opens on the first subscriber and stays open for the window's life | Closing when the last subscriber leaves | React's development double-mount would open, close and reopen sockets. The overlay subscribes for its whole life anyway, and an idle socket costs nothing noticeable. |
| `plan` records on the state stream | Accepted into a latest-plan slot | Ignored as an unknown record type | The HUD hides its plan row until plans arrive (HLD open question). Accepting the recording's existing `plan` record shape now means the plan note appears as soon as the brain streams it, with no app release. |
| Events missed while reconnecting | Not recovered | Re-reading the recording to backfill | Live surfaces show the latest state and the round summary, and neither depends on event history. The recording is the full record for after-set screens. |
| Where status comes from | Health polling every 5 s plus call outcomes | Health polling only; call outcomes only | Polling notices a service coming back while no screen is asking. Call outcomes mark a service offline the moment a screen hits it, without waiting for the next poll. |
| Network connectivity gating | Calls run whatever connectivity the browser reports | TanStack Query's default of pausing calls while the browser reports no internet | The services run on localhost or a direct venue link. A machine with no internet route still reaches every service, so pausing would freeze every screen at a venue without internet. |
| Reading a stream's status | Counts as a subscriber and opens the stream | An `idle` status before any subscriber | A status view showing `connecting` while nothing is trying would mislead. Opening the stream makes the status it shows real. |
| Concurrent `analyze` calls for one session | Share one request | Let each call through | One analysis is minutes of scoring and writes `data/reports/`. A double press should not start two. |
| 404 from `GET /reports/{id}` | Resolves `null` | A `not_found` failure | The contract defines that 404 as "not analyzed yet", a normal state the replay analysis screen designs for by offering to analyze. |
| Opening a stream socket | Abandon an attempt after 3 s | The browser's own connect timeout | A host that drops packets to a closed port leaves the attempt pending until the operating system gives up, about 75 s on macOS. The brain's API comes and goes with each match, so the app must notice it within seconds. 3 s is far above a connect over the venue link or Tailscale. |
| Where the round break is tracked | One hook in the service clients | In each consumer (the overlay's card, the main window's voice) | The voice and the card must start and end on the same records. One definition keeps them from drifting. |
| End of the last round break of a set | When the round stops being live (2 seconds without states), or at a state for another set | Held until the next set starts | No `round_start` follows a set's final KO; the brain stops the state stream once the game leaves the match. A break held over the results screen and menus would keep the coach's voice and the card alive past the set. |

## Open Questions & Future Decisions

### Deferred
1. Looking up recorded state at a frame, for clip timestamps that jump to a moment. Designed with the sessions screen, which decides what a jump shows.
2. Role values in `/coach/chat` history. `contracts/api.md` gives entries as `{role, text}` without naming the roles. The coach screen sends `user` and `coach` until the replay service states what it expects.
3. The `totals` object in `/stats`. `contracts/api.md` gives it as "same keys" as a round entry. It is typed as a round entry without `round`.

### Open questions
1. **The mock starts the next round one frame after each `round_end`.** Against `tools/mock`, a round break opens and ends almost at once, so the between-round voice and card cannot be heard or seen there. Seeing them needs a round-end pause in the mock's playback.
2. **A `round_end` sent while the state socket is down is lost** (events are not recovered), so that round gets no break, no voice and no card.

## References

- `../../high-level-design.md`: System Design, Where each surface gets its data, Key Design Decisions
- `../shell/shell-design.md`: the bridge and address resolution
- `../../../../contracts/api.md`, `../../../../contracts/recording.md`, `../../../../contracts/*.schema.json`
