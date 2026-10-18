# Service clients specs

Design: `service-clients-design.md`

## Addresses

- [ ] **CLIENT-ADDR-001**: The service clients shall read each service's address from `window.kumite.services` (provided by the shell's preload bridge) once, when the services module loads.
- [ ] **CLIENT-ADDR-002**: If `window.kumite` is absent, as when the renderer runs in a plain browser, then the service clients shall use `http://localhost:8765` for the brain, `http://localhost:8766` for replay and `http://localhost:8767` for analytics, each with source `default` and no warning.
- [ ] **CLIENT-ADDR-003**: The service clients shall build each brain stream URL from the brain address by replacing `http:` with `ws:` or `https:` with `wss:` and appending the stream path, `/ws/state` or `/ws/coach`.

## Contract types

- [ ] **CLIENT-TYPES-001**: The service clients shall define a TypeScript type for each schema file in `contracts/`: gamestate, event, session, round_summary, report, metrics, profile, gameplan and config.
- [ ] **CLIENT-TYPES-002**: The service clients shall define a TypeScript type for each shape `contracts/api.md` defines without a schema file: the `/health` reply, the coach message on `/ws/coach`, the `/coach/chat` request and reply, the `/stats` reply and the `/trends` reply.
- [ ] **CLIENT-TYPES-003**: In each contract type, a property outside its schema's `required` list shall be optional, a string `enum` shall be a union of its literal values, and a type that allows `null` shall include `null`.
- [ ] **CLIENT-TYPES-004**: Every service client call and brain stream shall deliver its values typed with the contract types.
- [ ] **CLIENT-TYPES-005**: The service clients shall define `InsightsV1` and its parts as a provisional type mirroring the insights draft schema, outside the types built from `contracts/`, with `focus.min_opportunities` optional.

## HTTP calls

- [ ] **CLIENT-HTTP-001**: The brain client shall provide `listSessions` (`GET /sessions`), `getSession` (`GET /sessions/{id}`), `getRecording` (`GET /sessions/{id}/recording`), `getProfiles` (`GET /profiles/{player}`), `getConfig` (`GET /config`) and `postConfig` (`POST /config`).
- [ ] **CLIENT-HTTP-002**: The replay client shall provide `getReport` (`GET /reports/{id}`), `analyze` (`POST /analyze/{id}`) and `chat` (`POST /coach/chat`).
- [ ] **CLIENT-HTTP-003**: The analytics client shall provide `getStats` (`GET /stats/{id}`), `getTrends` (`GET /trends/{player}/{character}` with an optional `stat` query value) and `getLearning` (`GET /learning/{id}`).
- [ ] **CLIENT-HTTP-004**: The service clients shall provide a `health` call (`GET /health`) for each of the brain, replay and analytics services.
- [ ] **CLIENT-HTTP-005**: The service clients shall time out `health` calls after 2 s, `analyze` after 5 minutes, `getRecording` and `chat` after 60 s, and every other call after 10 s.
- [ ] **CLIENT-HTTP-006**: The service clients shall percent-encode every path segment and the `stat` query value they put in a request URL.
- [ ] **CLIENT-HTTP-007**: The service clients shall send every request body as JSON with `Content-Type: application/json`.
- [ ] **CLIENT-HTTP-008**: When `postConfig` is called, the brain client shall send only the config fields the caller passed.
- [ ] **CLIENT-HTTP-009**: When `getReport` receives HTTP 404, the replay client shall resolve `null`.
- [ ] **CLIENT-HTTP-010**: When `analyze` is called for a session while an earlier `analyze` call for the same session is still in flight, the replay client shall return the earlier call's pending result without sending a second request.
- [ ] **CLIENT-HTTP-011**: For every call except `getRecording`, when a 2xx response arrives, the service clients shall resolve with its JSON value as the service sent it, without reordering, filtering or computing values.
- [ ] **CLIENT-HTTP-012**: The service clients shall not validate response fields against the contract schemas at run time.
- [ ] **CLIENT-HTTP-013**: The analytics client shall provide `getInsights` (`GET /insights/{id}?limit=3`) with the 10-second timeout.

## Failures

- [ ] **CLIENT-ERR-001**: If a service client call fails, then it shall reject with a `ServiceError` that names the service, the call, and exactly one kind: `offline`, `timeout`, `not_found`, `http` or `bad_response`.
- [ ] **CLIENT-ERR-002**: If a service client request gets no HTTP response because of a network failure, such as a refused connection or an unknown host, then the call shall reject with kind `offline`.
- [ ] **CLIENT-ERR-003**: If a service client call's timeout elapses before its response is complete, then the call shall reject with kind `timeout`.
- [ ] **CLIENT-ERR-004**: If a service client call other than `getReport` receives HTTP 404, then the call shall reject with kind `not_found`.
- [ ] **CLIENT-ERR-005**: If a service client call receives a non-2xx status other than 404, then the call shall reject with kind `http`, carrying the status code and the server's message: the `detail` field of a JSON error body when present (as JSON text when it is not a string), otherwise the body, either one cut to its first 200 characters.
- [ ] **CLIENT-ERR-006**: If a service client call other than `getRecording` receives a 2xx response whose body is not JSON, or is not the call's expected top-level kind (object or array), then the call shall reject with kind `bad_response`.

## Recording reader

- [ ] **CLIENT-REC-001**: When `getRecording` is called, the brain client shall read the response body as a stream and parse it one line at a time, without holding the whole body as one string.
- [ ] **CLIENT-REC-002**: While reading a recording, the brain client shall skip blank lines.
- [ ] **CLIENT-REC-003**: While reading a recording, the brain client shall skip and count every non-blank line that does not parse as a JSON object, including a truncated last line.
- [ ] **CLIENT-REC-004**: While reading a recording, the brain client shall skip every record whose `t` is not `state`, `event`, `tactical`, `plan` or `round_summary`.
- [ ] **CLIENT-REC-005**: When `getRecording` resolves, its result shall hold the session id it was called with, the `event`, `round_summary`, `plan` and `tactical` records in one array per type in file order, and the count of skipped lines.
- [ ] **CLIENT-REC-006**: Where the caller of `getRecording` passes `states: true`, the result shall also hold the `state` records in file order.
- [ ] **CLIENT-REC-007**: Where the caller of `getRecording` does not pass `states: true`, the brain client shall discard `state` records as it reads them.
- [ ] **CLIENT-REC-008**: The brain client shall keep fields that are not in the contract types on recording records, unchanged.

## Live streams

- [ ] **CLIENT-LIVE-001**: When the first subscriber in a window subscribes to a brain stream (state, `/ws/state`, or coach, `/ws/coach`), the client shall open that stream's socket.
- [ ] **CLIENT-LIVE-002**: The client shall keep each brain stream that has had a subscriber in a window connected for the rest of that window's life, including after its last subscriber leaves.
- [ ] **CLIENT-LIVE-003**: When a brain stream's socket closes or fails to open, the client shall retry after a wait that starts at 0.5 s and doubles after each failed attempt, up to 5 s.
- [ ] **CLIENT-LIVE-004**: When a brain stream's socket opens, the client shall reset that stream's retry wait to 0.5 s.
- [ ] **CLIENT-LIVE-005**: Each brain stream shall report its status as `connecting` before its first socket opens, `open` while a socket is open, and `reconnecting` from when an open socket closes until a new one opens.
- [ ] **CLIENT-LIVE-006**: If a brain stream frame is not a JSON object with a string `t`, then the client shall ignore it.
- [ ] **CLIENT-LIVE-007**: When a `state` record arrives on the state stream, the client shall replace the latest-state slot and notify every state subscriber.
- [ ] **CLIENT-LIVE-008**: When an `event` record arrives on the state stream, the client shall pass it to every event listener in arrival order without storing it.
- [ ] **CLIENT-LIVE-009**: When a `coach` record arrives on the coach stream, the client shall replace the latest-coach slot and pass the record to every coach listener.
- [ ] **CLIENT-LIVE-010**: When a `round_summary` record arrives on the coach stream, the client shall replace the latest-summary slot and pass the record to every summary listener.
- [ ] **CLIENT-LIVE-011**: When a record arrives on a brain stream with a `t` that stream does not carry (anything but `state`, `event` and `plan` on the state stream; anything but `coach` and `round_summary` on the coach stream), the client shall ignore it.
- [ ] **CLIENT-LIVE-012**: Each brain stream slot (latest state, latest plan, latest coach, latest summary) shall hold its most recent record and the wall-clock time the window received it, and shall be empty until its first record arrives.
- [ ] **CLIENT-LIVE-013**: The client shall not clear a brain stream slot when the stream reconnects or when records from a different session arrive.
- [ ] **CLIENT-LIVE-014**: The client shall not recover events the brain sent while a stream's socket was down.
- [ ] **CLIENT-LIVE-015**: When a `plan` record arrives on the state stream, the client shall replace the latest-plan slot.
- [ ] **CLIENT-LIVE-016**: If a brain stream's socket has not opened within 3 seconds of the attempt starting, then the client shall close it and treat the attempt as a failed open.

## Live set and round break

- [ ] **CLIENT-ROUND-001**: The `useRoundBreak` hook shall treat the `session_id` of the latest `state` record on the state stream as the live set.
- [ ] **CLIENT-ROUND-002**: The `useRoundBreak` hook shall consider a round live while the latest `state` record was received less than 2 seconds ago, re-checking every 250 ms.
- [ ] **CLIENT-ROUND-003**: When a `round_end` event for the live set arrives on the state stream, the `useRoundBreak` hook shall open a round break for that event's round, recording the time the event arrived and whether its `detail.match_over` is `true`, and replacing any round break already open.
- [ ] **CLIENT-ROUND-004**: When a `round_start` event for the round break's set arrives while a round break is open, the `useRoundBreak` hook shall end the round break, whatever the event's round.
- [ ] **CLIENT-ROUND-005**: When a `state` record for the round break's set arrives with a round later than the break's, the `useRoundBreak` hook shall end the round break.
- [ ] **CLIENT-ROUND-006**: When a `state` record for a set other than the round break's arrives, the `useRoundBreak` hook shall end the round break.
- [ ] **CLIENT-ROUND-007**: When the round stops being live while a round break is open, the `useRoundBreak` hook shall end the round break.
- [ ] **CLIENT-ROUND-008**: The `useRoundBreak` hook shall return the latest-state slot, the live set, whether a round is live, and the open round break or none.

## Service status

- [ ] **CLIENT-STATUS-001**: Each window shall track, for each of the brain, replay and analytics services, a status of `unknown`, `online` or `offline`; the address with its source and any warning; the last-checked time; and the `service` name and `version` from the last successful `/health` reply.
- [ ] **CLIENT-STATUS-002**: Each service's status shall be `unknown` until the first health reply or call outcome for that service in the window.
- [ ] **CLIENT-STATUS-003**: When the services provider mounts in a window, the status tracker shall call `/health` on all three services, then again every 5 s.
- [ ] **CLIENT-STATUS-004**: When a `/health` call returns a 2xx response whose body has `ok: true`, the status tracker shall set that service `online`.
- [ ] **CLIENT-STATUS-005**: When a `/health` call fails for any reason, including a timeout, or returns a body without `ok: true`, the status tracker shall set that service `offline`.
- [ ] **CLIENT-STATUS-006**: When any service client call fails with kind `offline`, the status tracker shall set that call's service `offline` at once.
- [ ] **CLIENT-STATUS-007**: When a service client call other than `/health` receives any HTTP response, including an error status, the status tracker shall set that call's service `online`.
- [ ] **CLIENT-STATUS-008**: When a service client call other than `/health` fails with kind `timeout`, the status tracker shall leave that call's service status unchanged.
- [ ] **CLIENT-STATUS-009**: When the status tracker sets a service's status from a health reply or a call outcome, it shall set that service's last-checked time to that moment.
- [ ] **CLIENT-STATUS-010**: The status tracker shall track the brain's service status separately from the status of its two streams.

## React bindings

- [ ] **CLIENT-HOOK-001**: The service clients shall provide a services provider component that wraps a window's root, owns that window's TanStack Query client, and starts the status tracker's health polling.
- [ ] **CLIENT-HOOK-002**: The service clients shall provide the query hooks `useSessions`, `useSession`, `useRecording`, `useProfiles`, `useConfig`, `useReport`, `useStats`, `useTrends` and `useLearning`, each running its matching client call.
- [ ] **CLIENT-HOOK-003**: When a query hook's call fails, the hook shall expose the call's `ServiceError` as its error.
- [ ] **CLIENT-HOOK-004**: Every query key the hooks use shall start with its service's name: `brain`, `replay` or `analytics`.
- [ ] **CLIENT-HOOK-005**: When a service's status changes from `offline` to `online`, the services provider shall refetch that service's queries in use and no other service's queries.
- [ ] **CLIENT-HOOK-006**: The query and mutation hooks shall not retry a failed call automatically.
- [ ] **CLIENT-HOOK-007**: While `useConfig` is mounted, it shall refetch the brain's config every 5 s.
- [ ] **CLIENT-HOOK-008**: When a `usePostConfig` call succeeds, the hook shall write the merged config the brain returned into the config query, and before that it shall leave the config query unchanged.
- [ ] **CLIENT-HOOK-009**: When a `useAnalyze` call succeeds, the hook shall write the returned report into that session's report query.
- [ ] **CLIENT-HOOK-010**: The `useChat` hook shall write no request or reply into the query cache.
- [ ] **CLIENT-HOOK-011**: The service clients shall provide `useLiveState`, `useLatestPlan`, `useLatestCoach` and `useLatestSummary`, each returning its brain stream slot's current value and re-rendering when that slot changes.
- [ ] **CLIENT-HOOK-012**: The service clients shall provide `useEventListener`, `useCoachListener` and `useSummaryListener`, each registering a listener on its brain stream for as long as the calling component is mounted.
- [ ] **CLIENT-HOOK-013**: The service clients shall provide `useStreamStatus` and `useServiceStatus`, each returning the current status of a brain stream or a service and re-rendering when it changes.
- [ ] **CLIENT-HOOK-014**: When a component calls `useStreamStatus` for a brain stream, the hook shall count as a subscriber to that stream, opening its socket if it is not yet open.
- [ ] **CLIENT-HOOK-015**: The query and mutation hooks shall run their calls whatever network connectivity the browser reports.
- [ ] **CLIENT-HOOK-016**: The service clients shall provide `useInsights(sessionId, enabled)`, a query hook keyed `['analytics', 'insights', sessionId]` that runs `getInsights` only while enabled and the id is non-empty.

## Implemented in

All paths are under `src/renderer/src/services/`.

| Spec IDs | Entry point |
|---|---|
| CLIENT-ADDR-001 – CLIENT-ADDR-003 | `addresses.ts` |
| CLIENT-TYPES-001 – CLIENT-TYPES-005 | `contracts.ts` |
| CLIENT-HTTP-001 | `brain.ts`, with `getRecording` in `recording.ts`; both gathered as `brain` in `calls.ts` |
| CLIENT-HTTP-002, CLIENT-HTTP-009, CLIENT-HTTP-010 | `replay.ts` |
| CLIENT-HTTP-003, CLIENT-HTTP-013 | `analytics.ts` |
| CLIENT-HTTP-004 | `status.ts` (`health`) |
| CLIENT-HTTP-005 | `http.ts` (`TIMEOUTS`), applied by each call |
| CLIENT-HTTP-006, CLIENT-HTTP-007, CLIENT-HTTP-011, CLIENT-HTTP-012 | `http.ts` (`exchange`, `requestJson`) |
| CLIENT-HTTP-008 | `brain.ts` (`postConfig`) |
| CLIENT-ERR-001 – CLIENT-ERR-006 | `http.ts` (`ServiceError`, `exchange`, `requestJson`) |
| CLIENT-REC-001 – CLIENT-REC-008 | `recording.ts` (`getRecording`) |
| CLIENT-LIVE-001 – CLIENT-LIVE-016 | `streams.ts` (`BrainStream` and the slots and channels it feeds) |
| CLIENT-STATUS-001 – CLIENT-STATUS-005, CLIENT-STATUS-009, CLIENT-STATUS-010 | `status.ts` (`serviceStatus`, `health`, `startHealthPolling`) |
| CLIENT-STATUS-006 – CLIENT-STATUS-008 | `http.ts` (outcome reporting), applied in `status.ts` |
| CLIENT-HOOK-001 – CLIENT-HOOK-016 | `hooks.tsx`; the provider wraps the root in `src/renderer/src/main.tsx` |
| CLIENT-ROUND-001 – CLIENT-ROUND-008 | `hooks.tsx` (`useRoundBreak`) |
