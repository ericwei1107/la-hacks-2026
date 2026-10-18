# Sentry evidence draft

Analytics retains real functional endpoint transactions and operation spans. Replay's accepted evidence is a real HTTP → coach-agent → OpenAI Responses → HTTP-client trace with actual model/usage, outcome, release and environment. Its exact retained URLs and owner PR #16 record are linked in `../SENTRY_VERIFICATION.md`.

The successful replay run used a temporary nano model override. One of three reported nano HTTP attempts selected a provider tip; the others fell back. The default mini model exceeded the owner timing budget. The grounded local fallback and current one-second provider budget remain approved. Historical trace evidence is preserved without relabelling it as the separately requested Luna migration.

**Brain evidence received and the trace verified (October 18).** A `game.decision` transaction with read, decode, reflex, tactical and input spans, release = deployed main SHA `e8f134fb…`, environment `demo-laptop`, 5% sampling. Owner-measured frame-loop timing over about 2600 frames each: p50 0.517 → 0.698 ms and p95 0.838 → 1.398 ms with tracing off → on, both far under the 16.7 ms frame budget, with the same over-budget and missed-frame counts. Before publishing, save the waterfall screenshot and get Sahil's acceptance statement; transport-unavailable behavior is unreported.

Until those artifacts have been checked, describe the integration as partial. Independent per-service traces do not establish distributed propagation. Native demo-environment and spoken-timing observations are separate from trace retention. Add the accepted brain evidence and owner-reviewed completion wording before publishing a full sponsor claim.
