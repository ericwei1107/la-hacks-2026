# Retained Sentry evidence

Canonical measurements, releases, environments and completion boundaries are in [Sentry verification](../SENTRY_VERIFICATION.md).

| Evidence | Retained trace |
| --- | --- |
| Replay: real HTTP → agent → OpenAI provider, `provider_selected` | [bc9fad3bd3974dbb9145165d02f9605c](https://university-of-maryland-ma.sentry.io/explore/traces/trace/bc9fad3bd3974dbb9145165d02f9605c/) |
| Replay: local fallback after attempted provider | [00d6272017d44356b3f2a3528afea8a4](https://university-of-maryland-ma.sentry.io/explore/traces/trace/00d6272017d44356b3f2a3528afea8a4/) |
| Replay: local fallback after attempted provider | [ce7223b81fc04a5f96d800d1b7416392](https://university-of-maryland-ma.sentry.io/explore/traces/trace/ce7223b81fc04a5f96d800d1b7416392/) |
| Analytics: learning operations | [85a2e87cec20477d868bd9357e49ff22](https://university-of-maryland-ma.sentry.io/explore/traces/trace/85a2e87cec20477d868bd9357e49ff22) |
| Analytics: trend reduction | [51e9f084479546a8af692a4eb5fd22b8](https://university-of-maryland-ma.sentry.io/explore/traces/trace/51e9f084479546a8af692a4eb5fd22b8) |
| Analytics: stats reduction | [b691a435513a4a1fae004482c2fd4077](https://university-of-maryland-ma.sentry.io/explore/traces/trace/b691a435513a4a1fae004482c2fd4077) |

Replay traces were independently checked October 18, 2026 with Sentry MCP; analytics links retain their earlier verification dates in the canonical record. Replay instrumentation is in merged [PR #15](https://github.com/ericwei1107/la-hacks-2026/pull/15), and the authoritative [owner evidence record](https://github.com/ericwei1107/la-hacks-2026/blob/4787b3268d8bc086653b66b62d6039c8c899a7f0/replay/SENTRY_VERIFICATION.md#retained-live-evidence-2026-10-18) is in merged [PR #16](https://github.com/ericwei1107/la-hacks-2026/pull/16). Its successful run used a temporary nano override in `development` on port 8776. Local fallback and the existing one-second budget are approved; demo voice verification and the requested Luna migration remain separate owner work.

**Pending:** Sahil's real read/decode/reflex/tactical/input decision trace, waterfall screenshot and tracing on/off timing comparison. No game screenshot exists here yet. Store the game waterfall here when real owner evidence exists, keeping credentials out of the image.
