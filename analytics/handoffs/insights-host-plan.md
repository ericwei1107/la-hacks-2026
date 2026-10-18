# Insights review and demo-data remediation

Requested October 18, 2026. Scope: publish Eric's existing implementation and concrete examples for Chloe's review, and make analytics' access to Sahil's live data verifiable. This covers the original C3 prerequisite and E4 host task; the revised parallel plan calls these E0/E1/E6.

## Context checked

Refreshed `origin/chloe` at `6e66871` and `origin/chloe-eric` at `914fc5e`. Both contributions are already present on Eric at `c87dcbe`; neither branch has newer work. Chloe's static acceptance note confirms throw/history display behavior, and explicitly leaves growing-session flushes and live refresh unobserved. The current main branch does not yet contain these Eric-branch merges.

## Implementation sequence and acceptance

1. Publish the existing shared reducer, evidence/focus builder, internal schema, proposal and tests. Preserve calculation version 4 and existing APIs. Chloe must be able to fetch a named commit and run the exporter without receiving local files.
2. Generate review fixtures through `InsightRepository`, including real and synthetic sessions, early/no opportunities, invalid data, pending/current learning, manual focus and event-only moments. Check them into `analytics/fixtures/insights/` with a regeneration/drift test. Supply field/display rules and a TypeScript sketch. Preserve draft advice status and distinguish this review from Chloe's acceptance.
3. Run analytics on Sahil's Windows host with the brain's absolute `DATA_DIR`. Add a portable launcher that validates the existing directory and sets it before importing analytics. Add a read-only proof that local metadata/recording content matches the brain, and that remote stats/learning match that local source. A healthy `/health` alone cannot prove any of these.
4. Verify a temporary growing canonical data folder through actual brain/analytics HTTP routes: recording flush first, learning flush later, partial tails, and a deliberate wrong-folder/content case. Unit tests cover fixture drift, bad paths, source races, missing learning, identities and diagnostics. Run the full offline suites, frozen example validation and existing smokes on the combined change.
5. Publish named commits on an isolated review branch based on Eric and open a review PR. Record exact commands and remaining host observations. The native live run still requires Sahil's actual directory, reachable host and a growing session. Retain source parity, advancement, reconnect, session-switch and shutdown observations before closing E4/native acceptance.

## Decisions and dependencies

Use host-local files on Sahil's laptop; Chloe's app connects over the existing service URLs. This avoids making a remote file-sync mechanism part of the live path. Existing HTTP recording access is used only for read-only identity verification. No filesystem path or credentials are added to `/health`.

The insight format and examples remain review drafts. A public route and app live consumer require the existing four-owner interface agreement. Experimental routes and producer changes are separate decisions in the parallel plan. The checker reset issue remains documented for its owner; this remediation adds an independent snapshot/source check and does not claim to correct that watcher.

Host-specific inputs requested from Eric: absolute brain `DATA_DIR`, Tailscale hostname/IP, and availability through an existing remote connection. Never publish the actual host's private configuration or credentials.

## Publication isolation

Another writer changed the shared builder/schema and added experimental API files after the passing regression run. The tested builder and schema were recovered into an isolated checkout, with SHA-256 hashes exactly matching the verified originals. Later API changes and their new schema/generator remain intact in the original workspace. This handoff branch includes the internal export and examples, launcher and source proof; it changes no existing HTTP handler. The isolated tree is revalidated before publication.
