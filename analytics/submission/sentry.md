# Sentry evidence draft

Analytics retains real functional endpoint transactions and operation spans. Replay's accepted evidence is a real HTTP → coach-agent → OpenAI Responses → HTTP-client trace with actual model/usage, outcome, release and environment. Its exact retained URLs and owner PR #16 record are linked in `../SENTRY_VERIFICATION.md`.

The successful replay run used a temporary nano model override. One of three reported nano HTTP attempts selected a provider tip; the others fell back. The default mini model exceeded the owner timing budget. The grounded local fallback and current one-second provider budget remain approved. Historical trace evidence is preserved without relabelling it as the separately requested Luna migration.

**Brain evidence remains pending.** Sahil must return the real five-operation decision trace and matching waterfall, full deployed main SHA, `demo-laptop` environment, 5% deployed sampling configuration and comparable p50/p95 on/off decision-loop timings. Transport-unavailable behavior and his overhead acceptance must also be retained.

Until those artifacts have been checked, describe the integration as partial. Independent per-service traces do not establish distributed propagation. Native demo-environment and spoken-timing observations are separate from trace retention. Add the accepted brain evidence and owner-reviewed completion wording before publishing a full sponsor claim.
