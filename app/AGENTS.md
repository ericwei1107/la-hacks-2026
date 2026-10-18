# Kumite desktop app (Track B)

This folder is the Kumite desktop app, owned by Chloe. The repo-root `CLAUDE.md` applies here in full: edit only `app/`, treat `contracts/` as frozen, keep code files free of comments, never commit keys or `.env` files. This file adds the app's own design workflow on top of those rules and treats `app/` as the project root for every path below.

## LID
- Mode: Full
- Version: 1.4.0

## Linked-Intent Development (MANDATORY)

**Consult the `linked-intent-dev` skill for ALL code changes in `app/`.** All changes flow through the arrow of intent in one direction:

```
HLD → LLDs → EARS → Code
```

- **All changes**: consult the `linked-intent-dev` skill. The workflow in one line: HLD check → LLD → EARS specs → edge audit → code, inspected by Chloe at each phase.
- **Tests**: this project writes no automated tests. The tests-first phase is skipped by owner decision; coherence verification at the end of a change is a read-through of spec against code, and a spec is marked `[x]` only after that read-through and Chloe's review.
- **Bug fixes**: walk the arrow like any other change — find where behavior diverged from intent and cascade from there. No short-circuit.

Each phase's output is inspected — by the user or an inspector they name — before the next begins; ambiguous spec readings go back to the user. **Docs carry current intent, written to be read cold** — write each doc as if authored fresh today, from current intent alone: no narration of how it changed, no meaning that needs the conversation that produced it, no rebuttals to questions only a past discussion raised. Rationale, considered alternatives, and constraints a fresh author would independently write stay; record rejected alternatives and why in the LLD's Decisions & Alternatives table, not as asides in body prose.

**Memory vs. intent.** Before saving durable project knowledge to agent or tool memory, test whether it is project *intent* — would a fresh agent, in any tool, next session, need it to build this system correctly? If yes, record it in the arrow (HLD / LLD / EARS / decision doc), which travels and cascades — not in private, per-tool memory, where intent escapes the arrow. Knowledge about the user or how they like to work stays in memory.

### Navigation

| What you need | Where to look |
|---|---|
| Team-wide design (all four tracks) | `../prep/design-doc.md`, local only, never committed; Sections 13 and 18.2 cover this app |
| Service and data contracts | `../contracts/api.md`, `../contracts/recording.md`, `../contracts/*.schema.json` |
| High-level design | `docs/high-level-design.md` |
| Design tree (sub-HLDs, LLDs, their specs) | `docs/intent/` — one folder per node |
| EARS specs | beside each design doc as `{node}-specs.md` in the node's folder under `docs/intent/` |
| Decision docs | `docs/decisions/` (project-level) and `docs/intent/<segment>/decisions/` |

### Terminology

- **HLD**: High-Level Design — single project-level doc at `docs/high-level-design.md`.
- **LLD**: Low-Level Design — detailed component design doc in `docs/intent/`. The design layer is a recursive tree: the root is the HLD, leaf LLDs own EARS, and a component deep enough to outgrow one doc becomes a sub-HLD (HLD-shaped, owns no EARS) with children beneath it. "HLD" and "LLD" are roles by position; depth-2 (one HLD over flat leaf LLDs) is the default.
- **EARS**: Easy Approach to Requirements Syntax — structured one-line requirements beside each design doc as `{node}-specs.md` in the node's folder under `docs/intent/`. IDs are path-concatenated — the root-to-leaf path of the owning segment plus a number — so a prefix grep gathers a subtree. Markers: `[x]` implemented, `[ ]` active gap, `[D]` deferred.
- **Arrow**: the unidirectional chain from vision to code (HLD → LLDs → EARS → Code). Strictly a DAG of intent.
- **Arrow segment**: the territory owned by one leaf LLD — the LLD itself plus the specs and code that implement its EARS IDs. The boundary is the leaf prefix. Within-segment cascade is free; across-segment cascade pauses.
- **Cascade**: propagating a change downstream through the arrow so adjacent levels stay coherent.

### Spec-to-code links

Code files carry no comments, so code holds no `@spec` annotations. The link runs the other way: each `{node}-specs.md` lists, under an `## Implemented in` heading, the entry-point file (and exported function or component, where one file holds several behaviors) for each spec ID. Point at the topmost module that owns the behavior, not every helper. When code moves or is renamed, update that list in the same change.
