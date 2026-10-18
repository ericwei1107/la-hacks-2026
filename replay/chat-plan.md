# Evidence-grounded coach chat implementation plan

Build POST /coach/chat using the frozen inline API contract, accepting session_id, player, message and user/coach history. Only replay/ changes; preserve characters, contracts and Claude's lookup modules.

- [x] Add failing endpoint and tool tests covering real human slots, history roles, verified round/frame citations, missing reports/learning, invalid sessions, unknown moves, provider failures and bounded tool calls.
- [x] Add session-scoped read-only tools for habits, mastery, moments, exact state lookup, character frame data, hypothetical punishers and analytics learning curves. Resolve DATA_DIR safely. Use original recording events for actions/citations; never run Jev or analysis implicitly. Mark unavailable and synthetic data.
- [x] Add a small Responses API tool loop using the installed SDK. Map coach history to assistant. The model selects server-generated evidence facts by ID; the server composes only those verified sentences and their citations. Limit tool rounds, total calls, model time and answer length. Unknown IDs, API errors and timeouts use deterministic retrieval rather than unconstrained model text.
- [x] Add the route, response models, local mode, configuration/run documentation and an offline neutral-sample HTTP check. Chat answers have their own length/time budgets; round coaching remains at 20 words and one second.
- [x] Run focused and full replay tests, frozen-contract checks and independent review. Real live-learning verification remains pending sample availability. No paid verification without specific authorization.
