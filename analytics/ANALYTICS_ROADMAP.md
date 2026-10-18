# Kumite analytics implementation roadmap

Planning date: October 18, 2026, America/Los_Angeles. Owner: Eric, Track D. Inspected checkout: `c7e11f2` plus existing working-tree changes. This document proposes work; it does not claim implementation, new test runs, deployment, or teammate agreement.

**Outcome.** Help a player choose one useful practice target, inspect the exchanges behind that recommendation, and determine whether performance improves under comparable conditions. Explain bot adaptation separately from human improvement.

**Confirmed product choices.** Eric selected a demo-ready core followed by a broader roadmap, beginner/intermediate players choosing what to practice as the primary audience, and improvements to Chloe's existing Stats and Learning screens. Shared contracts and owner implementation still follow the ownership rules below.

**Ownership.** Eric implements analytics calculations, evidence extraction, mocks, historical analysis, exports and verification in `analytics/` and `tools/mock/`. Chloe owns presentation, interactions, refresh hooks and the app's intent/spec workflow. Sahil owns game signals, predictor/bandit instrumentation, training controls and the fine-tune/evaluation pipeline. Garrett owns move validation, report decisions, coaching and drills. Changes to frozen `contracts/` require all four owners' agreement. Draft handoffs for review; sending messages is a separate authorized action.

**Current foundation, inspected rather than newly reverified.**

| Capability | Present state | Consequence for this plan |
|---|---|---|
| File-backed stats, learning and trends | Implemented; shared reducer serves real/mock metrics | Extend the existing pipeline rather than duplicate formulas |
| Real M3 learning bundle | Local intake and approved cloud parity retained in `LIVE_LEARNING_VERIFICATION.md` | Use as the primary real-data acceptance fixture |
| Plain-low metric | Code is calculation version 4 | Preserve semantics; older remediation prose has stale version-3 statements |
| Tiger Data | Version-4 refresh and real-sample cloud parity documented | Maintain version/source checks; do not repeat infrastructure setup |
| Parquet archive B8 | Implemented and documented in `ARCHIVE.md` | Reuse for batch exploration; no new archive project is needed |
| Desktop Stats/Learning | Rates, damage bars, history, accuracy, habits and option estimates exist | Add evidence, counts, clarity and explicit refresh behavior |
| Replay report API | Published source exposes analyze/report routes; real report integration remains to be proved in the handoff | Core analytics must work when report analysis is unavailable |
| Sentry | Analytics/replay evidence retained; brain decision waterfall/timings and demo environment pending | Keep sponsor completion separate from player-facing readiness |
| Real retest and fine-tune results | Deliberate retests unverified; fine-tune comparison null in real sample | Display unavailable status until producer evidence exists |

**Real acceptance fixture.** `DATA_DIR=data/samples/live_learning`, session `2026-10-18T05-14-03_sahil_djin_vs_kaz`: four rounds; low blocks 0/16; throw breaks 1/4; current reducer's estimated punish conversions 0/6; prediction accuracy 0.60, 0.7333, 0.9048, 1.00; low-defense detection round 3; `after_block:any` first fixed in round 2 and regressed in round 3; no low-defense mastery and no fine-tune evaluation. Preserve the distinction between 16 raw low contacts and the producer's final habit observation count of 15. Validate the added counters independently against source events during implementation.

**Release slices.**

| Slice | Deliverable | Required work |
|---|---|---|
| A: trustworthy analytics package | Counts, definitions, evidence, snapshot export and mock parity | DA1–DA2 |
| B: useful desktop experience | One focus card, habit history, selectable moments and reliable freshness | DA3–DA5 plus Chloe integration |
| C: credible improvement tracking | Comparable-session history and a fixed-condition practice pilot | DA6–DA7 |
| D: advanced diagnosis | Context heatmaps, attempt funnels, precise timing and deliberate retests | DA9, gated by source quality and owner capacity |

Release B is the first user-facing milestone. DA8 operational readiness runs alongside it. If the deadline is extremely short, release A with a deterministic report export and existing screens is a concrete fallback. The remaining scheduling input is the actual demo deadline and available integration window; work-package order is defined without promising unsupported completion times.

**DA1 — Define measurements and expose their evidence. Priority: required. Owner: Eric; Sahil/Garrett validate mechanical interpretations.**

Produce a metric dictionary and extend the shared reduction path with successes, opportunities, failures, per-round values, and source references for low defense, throw defense and estimated punish conversion. Compute evidence and totals together so a chart and its drill-down cannot disagree. Proposed files: `analytics/stats.py`, a small `analytics/evidence.py`, and focused reducer tests. Final module boundaries should follow the existing code.

| Metric | Definition | Required interpretation |
|---|---|---|
| Low defense | Human blocks of bot plain-low contacts / bot plain-low block, hit and counter-hit contacts on the human | Contact defense, not every low selected or attempted; exclude special lows as version 4 does |
| Throw defense | Human successful breaks / bot throw attempts targeting the human | Break events do not add another attempt; flag impossible/orphan counts rather than hide them through rate capping |
| Estimated punish conversion | Existing unmatched unsafe-block opportunities paired with qualifying human hits in the same round | Preserve the provisional timing rule; do not label every match a guaranteed punish |
| Damage by situation | Recorded incoming damage grouped by recorded/derived situation | Describe context; do not claim all damage in a group is avoidable |
| Bot prediction accuracy | Producer's correct guesses / eligible guesses for that round | Bot performance; counts and baseline unavailable until supplied by Sahil |
| Current habit status | Latest producer `fixed`/mastery observation | Distinct from historical first-fixed round |
| Bot option estimate | Producer bandit's discounted, prior-adjusted damage reward estimate | Not a raw hit percentage or a player skill score |

Every metric record should identify its definition/calculation version, population, successes/opportunities when meaningful, nullable value, source snapshot, and evidence references. Keep model estimates in separate fields from observed frequencies. Evidence references include session, round, frame and source identity/line; round/frame alone is not unique. Do not collapse genuine simultaneous events using an overly broad deduplication key.

Define data states: `observed`, `no_opportunities`, `early_signal`, `unavailable`, and `invalid`. A skipped/truncated source is reported as quality information, not a fabricated zero. Unknown record extensions remain ignored by existing contract readers. Summaries supply round-level mastery transitions; timestamped free-form extensions need an explicitly supported adapter before they become precise timeline markers.

Acceptance: independently enumerate 0/16 lows, 1/4 throws and 0/6 estimated punishes in the real fixture; every counted opportunity links to the appropriate source record. Cover human slot 1, side switches, no opportunities, special lows, round resets, overlapping punish windows and orphan throw breaks. Preserve existing route values unless a separately reviewed bug correction is necessary. Any change affecting stored calculations must advance the calculation version and invalidate/recompute stale aggregates deliberately.

**DA2 — Package insights without breaking shared interfaces. Priority: required. Owner: Eric; team agrees integration interface. Depends on DA1.**

Start with a read-only command, provisionally `python -m analytics.insights <session_id> --data-dir <dir>`, that atomically writes an ignored `DATA_DIR/analytics/<session_id>.json` and prints a concise summary. This command and path are planned, not present commands. It should expose a documented versioned analytics snapshot with metric details, focus candidates, habit status/history, moments, quality and freshness information.

Draft the exact response examples in `analytics/INSIGHTS_PROPOSAL.md` before requesting cross-track agreement. Recommended eventual transport: an additive `GET /insights/{session_id}` for session detail and, in DA6, an additive filtered history route. Preserve `/stats`, `/learning` and `/trends`. Neither the route nor a shared sidecar file is an approved contract until owners agree. If approval is delayed, finish the internal export, tests and sample responses; the existing APIs remain usable.

Keep responses bounded: return a small default set of important moments, page detailed evidence, and avoid embedding the full recording. A snapshot must identify the consumed recording prefix and learning round. Reuse cached parsed sources and the existing file-replacement protections. Evidence references are scoped to their snapshot; stale selections trigger refresh rather than silently resolving against rewritten source data. Existing routes keep their current error semantics. Proposed insight failures must be concise and credential-free.

Do not call another service's coach model from the analytics request path. Use one shared implementation for the export, real endpoint and mock. Tactical records are not retained by the current stats/trend readers; if needed for adaptation detail, build a narrow validated adapter rather than assuming those records already reach reducers. Do not change unknown-record behavior globally.

Acceptance: deterministic output for unchanged sources; an appended complete event changes the appropriate snapshot; a partial tail waits; rewritten/deleted files cannot leave mismatched counts/evidence; real/mock/export agree; existing route regression checks pass. A missing report or database does not prevent file-backed session insights. Endpoint validation against its agreed schema is required before UI integration.

**DA3 — Recommend one focus and explain adaptation. Priority: required. Eric calculates; Chloe presents; Garrett validates training text. Depends on DA1–DA2.**

Implement a deterministic focus selector, provisionally `analytics/focus.py`. Start with low and throw defense; include punishment after its false-match audit. Use observed failed opportunities to rank eligible weaknesses, not an opaque composite score or an assumed amount of recoverable damage. Filter contexts where the metric does not support actionable advice. Return the reason, evidence and rule version.

Provisional product rule: automatic selection requires at least five eligible observations in the current set; one to four remain visible as an early signal. This threshold is a UI choice, not statistical significance or a mastery rule. Break ties consistently, let the player keep/select a focus, and change automatic focus only at round boundaries. If no eligible evidence exists, show that more observations are needed. Eric should confirm the focus-selection policy before implementation.

Focus card: one label, one fraction, one short action and a review link. Separate post-set examples from live coaching. Frame low-defense practice as recognizing low/mid choices, not crouching continuously. Use vetted templates initially; let Garrett's validated coach enrich them when available.

Build aligned bot/player histories: producer prediction accuracy above observed player defense outcomes, with detection/fixed/regressed markers. Show first fixed and current status separately. The real fixture must show that the bot learned to exploit low defense without falsely claiming that the player fixed it. All `player_changed` flags in this fixture are false; do not manufacture a drift marker.

If Sahil has not supplied live target state, label the target as the last completed-round observation. If predictor counts/baselines are absent, show the recorded percentage with an explicit unavailable-count detail; do not reconstruct integer counts from rounded percentages. Rename option bars to estimated effectiveness and explain that untried options may retain prior values.

Acceptance: the real fixture selects low defense under the provisional rule, explains 0/16, retains the after-block regression, and leaves fine-tune comparison unavailable. A loss may contain a useful positive observation; a win may still expose a weakness. No recommendation promises a win or a guaranteed damage reduction.

**DA4 — Make refresh, freshness and recovery explicit. Priority: required. Eric provides snapshot/readiness semantics; Chloe owns app hooks. Depends on DA2; parallel with DA3.**

Three update paths: state/events for the small active-round presentation; refresh after `round_summary` for authoritative completed-round metrics; closed-round imports for historical aggregates. Improve existing screens before adding navigation. Do not render a 60-Hz analytical dashboard or add synchronous database/model work to the game's hot loop.

On round end, invalidate relevant stats, learning, recording and history queries. Handle the race between a summary arriving and companion files being flushed: compare expected round with returned snapshot and perform bounded retries, then label pending/incomplete. Coalesce duplicate summary notifications. Active-session stats polling at roughly one to two seconds is optional and must be measured; historical sessions do not poll. State reception time and completed learning round must be shown independently.

On reconnect, refetch authoritative files/API snapshots. Do not try to recover exact aggregate totals by replaying an uncertain WebSocket buffer. Preserve last good values with a stale label, bind all updates to the selected session, and clean up subscriptions when switching. Round frame time is for gameplay; wall-clock receipt time is for connectivity. State gaps stay gaps.

Acceptance: app open before a round ends updates without manual reload; delayed learning flush transitions from pending to current; duplicate messages do not double counts; disconnect/reconnect converges to file totals; switching sessions cannot show another set's numbers. Run these checks on Sahil's actual Windows demo host. An initial performance target, subject to host measurement, is cached session-insight response p95 under 250 ms on a representative set and visible completed-round updates within two seconds after required files are available. These are targets, not current measurements.

**DA5 — Connect charts to useful moments. Priority: required for release B. Eric owns references; Garrett supplies report analysis; Chloe owns navigation. Depends on DA1–DA2.**

Use existing health timelines plus events for a selectable exchange timeline. Keep round boundaries and gaps visible. A selected moment shows the recorded event, preceding context, actual response, evidence quality and available suggested alternative. Basic event inspection works without a generated report. Report-backed `actual`/`best`/`why` and drill advice appear only after the real report endpoint has passed integration.

Verify Garrett's published implementation using the exact synthetic bundle in `handoffs/report-integration.md`, then the real M3 bundle. Validate reports and citations against the recording; distinguish model preferences and observed frequencies from calibrated win probabilities. Human-readable move recommendations must resolve to the character data. Unknown move IDs remain unknown.

Select a few important moments using transparent rules such as repeated focus failures and recorded high-damage exchanges; preserve source order in playback. A report failure leaves useful metrics/evidence available. Missing video means a data review, not fabricated footage. Recorded JSONL does not support arbitrary game-state restore or native replay takeover.

Acceptance: selecting a metric shows its contributing exchanges; selecting a marker resolves to the correct session/round/frame; displayed health context agrees with the source; unavailable report analysis has a clear fallback. The real fixture's fixed/regressed history is not confused with low-defense mastery.

**DA6 — Compare performance fairly across sessions. Priority: release C. Owner: Eric; Chloe integrates. Depends on DA1–DA2.**

Add comparable-session selection in a dedicated history reducer, provisionally `analytics/history.py`. Default to same player, human character, bot character, difficulty, game version and real/synthetic mode. Compare only compatible metric definitions. Exclude the current set and any later sessions from its baseline. Explicitly separate active/partial sets from completed historical results.

Use available session metadata first. Add training focus, prompt/assistance state, difficulty overrides and model/config identifiers to historical context only through owner-agreed producer records. When context is missing, label the baseline partially matched or unavailable; do not claim control of unrecorded conditions.

Pool successes/opportunities rather than averaging percentages. Display session count, opportunity count, timeframe and filters. Start with a small transparent recent-session window; return unavailable when insufficient comparable history exists. The window is configurable, with five comparable completed sessions as a provisional default. Do not invent global percentiles, rank equivalents or an ELO-like score from this dataset.

Keep file results authoritative. Extend Tiger Data snapshots/queries only if needed after the file reducer is validated; preserve source signatures, calculation versions, transactionality, backfill idempotency and file fallback. New stored raw telemetry or new cloud destinations need a separate scope check; the current upload approval does not automatically cover every future dataset. Reuse B8 for read-only historical exploration. Note that B8 recording archives do not include companion learning files, so a learning-history export must explicitly join those files or use a separately designed derived dataset.

Acceptance: different difficulties/opponents/versions and synthetic samples are excluded by default; no future-session leakage; 1/2 plus 9/10 produces 10/12; zero opportunities do not become zero skill; missing context is visible; database and file results agree, with the aggregate route proved separately from fallback.

**DA7 — Measure practice, retention and transfer. Priority: release C. Eric designs analysis; Eric/Sahil arrange practice; Chloe/Garrett support experience. Depends on DA3 and DA6.**

Create a small fixed-condition pilot: baseline block without targeted prompts, targeted practice, immediate unprompted check, delayed unprompted check, then a different relevant move/opponent check. Retention means the skill remains later; transfer means it works beyond the practiced example. Freeze the test configuration so the adaptive bot does not confound before/after comparisons; evaluate adaptive play separately.

Record a pseudonymous participant id, session IDs, test/practice phase, target skill, configuration/version, assistance state, opportunities and outcomes. Match conditions and opportunity definitions. Store attempts and prompt state explicitly; fixed/regressed events alone do not prove deliberate retests. Agree recording/share/cloud scope with Eric before collecting participant data.

Track the target metric and a balancing metric: improved low blocking accompanied by substantially more mid hits is not automatically improved defense. Also ask players to identify their next practice action and whether the display distracted them. Compare counts across blocks and retain individual results; an exploratory small pilot is not a population-level causal proof. If sample size permits later research, randomize feedback conditions and define the analysis before observing outcomes.

Acceptance: a complete pilot record has reproducible source-linked denominators, controlled conditions, prompt status and missing-data labels. Report human improvement separately from bot prediction quality and held-out fine-tune results. No improvement is a valid result and should not be hidden.

**DA8 — Finish operational and demonstration evidence. Priority: required alongside release B. Owner: Eric; runtime checks involve all owners.**

Complete the original B6 runbook and a small read-only health/freshness checker rather than replacing that work with new charts. Before integration, run team status; verify all three services, addresses/DATA_DIR, an active round's stats, a subsequent learning record, reconnect behavior and native Windows paths. Only stop temporary processes started for the check; owner-run services remain owner-controlled.

Finish B5's remaining brain decision trace, waterfall and tracing-on/off measurements with Sahil. Verify the demo environment separately. Retain analytics insight operation timings and credential-free diagnostics. A successful replay provider trace does not prove real-time brain instrumentation or player-facing readiness. Keep text-coach model migration/voice timing as the existing separate owner handoff.

Extend B7's proposed demo report into a deterministic evidence export containing source IDs/hashes, metric versions, human outcomes/counts, bot learning history, first/current mastery, null fine-tune status and representative moments. Support the real M3 detection/exploitation story immediately. A player-improvement story requires an additional actual improvement/retention recording; use synthetic data only with explicit labels.

Update README/Devpost/sponsor claims from measured output, with owner review. Reconcile stale status prose in `REMEDIATION.md` and the historical batch list without erasing older verification dates. B8 is complete; optional Spaces backup stays outside the critical path. Re-run archive conversion as new completed demo sessions arrive; do not change its source-preservation policy.

Acceptance: repeatable local and demo-host commands, correct environment, explicit source freshness, retained outputs and truthful claims; Tiger Data outage still permits local stats/learning; unknown/no-data states are legible at the actual video resolution. Sentry sponsor completeness and human-learning evidence each have their own gate.

**DA9 — Add deeper diagnosis only after the core is useful. Priority: optional.**

| Feature | Computation | Required gate |
|---|---|---|
| Distance × situation heatmap | Event-level success/failure fractions in existing distance/context buckets; selectable evidence | Counts, context quality and sample sizes visible; no per-frame attack double-counting |
| Punish recognition/attempt/success funnel | Separate estimated opportunity, observed attempt and successful response | Reliable input/attempt/recovery semantics agreed with Sahil; mechanical audit with Garrett |
| Response-timing distribution | Input onset or response onset relative to a validated opportunity window | Missing-frame/input coverage and window definition verified; do not call hit delay pure reaction time |
| Explicit drill/retest history | Prompted practice versus later unprompted probes | Producer records trial identity, target and prompt/retest state |
| Bot option trials/outcomes | Explicit attempts, settlements and damage reward context | Sahil supplies actual integer trial counters; discounted success/failure pseudo-counts are not trials |
| Predictor baseline and sample counts | Correct/total on the same eligible decisions, compared with a simple baseline | Producer captures counters/baseline before training on each decision; no reconstruction from rounded percentages |

Avoid a new overall skill score, global leaderboard, stage-wall map, match-win probability model, full replay takeover, new training infrastructure, or cloud backup in the first release. Each needs evidence or infrastructure beyond the core problem.

**Dependency and delivery order.**

`DA1 → DA2 → {DA3, DA4, DA5} → release B`

`DA1 + DA2 → DA6 → DA7 → release C`

`DA8 runs alongside release B; DA9 follows a demonstrated user need and producer readiness.`

Within Eric's lane, implement one cohesive change at a time: dictionary/evidence, internal snapshot export, agreed API/mock transport, focus selector, history, pilot/export. Chloe can design against example responses while backend work proceeds; Garrett can validate report references independently; Sahil can add agreed counters. This describes teammate scheduling, not authorization to edit their folders or spawn agents.

**Verification and release gates.**

| Gate | Evidence needed |
|---|---|
| Metric correctness | Independent source counts, meaningful event-pairing cases and real M3 regression assertions |
| Interface compatibility | Frozen examples unchanged; new examples/schema approved; old API consumers still work; mock parity |
| Evidence consistency | Totals, selected examples, source revisions and round/frame markers agree |
| Live behavior | Append/partial-tail/rewrite cases; round flush race; reconnect; session switching; Windows host observation |
| Model interpretation | Probability vs observation vs mastery vs reward labels; no invented baselines/evaluation/retests |
| Historical validity | Comparable contexts, pooled counts, no future leakage, explicit missing context |
| Operations | Measured latency/freshness, database fallback and separate retained Sentry evidence |
| User usefulness | Player can name one next action and find its evidence; practice outcomes measured honestly |

Use focused tests for new reducer behavior, then relevant analytics/mock suites and `contracts/validate.py`. The app owner follows `app/AGENTS.md`: no new app automated tests; intent/spec coherence and owner visual review instead. The existing smoke programs provide the baseline, but new insights and the round-flush race need their own meaningful integration coverage. Run cloud integration/backfill only when that implementation touches stored results and appropriate existing authorization covers the data.

**Requests to prepare for teammates.**

| Owner | Concrete request | What can ship without it |
|---|---|---|
| Chloe | Capacity for existing-screen changes; review response examples, count labels, status history, freshness and selected-moment behavior | Export and backend package |
| Sahil | Correct/total prediction counters and same-population baseline; optional active target signal; actual trial/retest/config context when extending those features | Recorded percentages, completed-round targets and observed defense counts |
| Garrett | Published report branch/service; validated advice for initial focus categories; confirm meaning of option scores/cost fields | Event/health review and vetted basic templates |
| All four | Review the proposed insight contract and any producer extensions | Internal calculation/export work |

**Eric's decisions.**

| Decision | Recommended default | When an answer is needed |
|---|---|---|
| Delivery horizon | Confirmed: demo-ready core first, then release C/D | Eric still needs to supply the actual demo deadline/integration window |
| Primary audience | Confirmed: beginner/intermediate players choosing what to practice | Settled |
| UI scope | Confirmed: improve existing Stats/Learning | Chloe supplies the owner implementation/integration window |
| Focus policy | Automatic evidence-based suggestion, player override, five-observation eligibility | Before DA3 ships; threshold remains a tunable product rule |
| First pilot skill | Low defense, with mid-hit outcomes monitored | Before DA7 data collection |
| Additional demo recording | Use existing detection/exploitation evidence; record a separate real improvement/retention block if time permits | Eric decides whether a further game-laptop session fits the deadline |
| Shared interface | Additive insights route after team agreement | Before DA2's shared integration phase |
| New participant/cloud data | Keep new pilot material local until scope is explicitly agreed | Before collection, sharing or new uploads |

Unanswered product choices can remain provisional while DA1's definitions and DA2's internal export are designed. Contract changes, teammate code, participant data collection and new uploads do not become authorized merely because a recommended default appears here.

**First implementation task.** DA1: add shared low/throw/punish counters and source-linked evidence, retain current semantics, verify the real fixture and document any anomalies. Deliver it as a small reviewable backend change before introducing a new chart or training control.

**Existing commands for baseline inspection; no new roadmap commands are implemented yet.**

```sh
.venv/bin/python -m unittest discover -s analytics/tests -p test_live_learning.py -v
.venv/bin/python contracts/validate.py
```

Expect the existing five real-learning regression tests and frozen contract examples to pass. These baseline checks do not prove the planned counts/evidence interface, new UI, or live demo-host integration.

**Research basis carried forward.** Task-specific feedback and linked trends from [Aimlabs](https://www.aimlabs.com/articles/aimlabs/aimlabs-1-3-2-patch-notes/); opportunity definitions from [Leetify](https://leetify.com/blog/leetify-stats-glossary/); focused skill development from [Mobalytics](https://mobalytics.gg/lol/guides/mobalytics-beginners-guide); contextual comparisons and event summaries from [Dota Plus](https://www.dota2.com/plus); actionable moment review from [Tekken](https://tk8.tekken-official.jp/mode/replay.php) and [Chess.com](https://support.chess.com/en/articles/8584089-how-does-game-review-work); reproducible practice context from [RefleK's](https://refleksapp.com/docs/automatic-tracking/). These are design precedents, not proof that Kumite's planned intervention improves players.
