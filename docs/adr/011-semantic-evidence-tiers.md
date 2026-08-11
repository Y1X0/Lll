# ADR-011 — Semantic evidence tiers, no auto-promotion

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

The platform must distinguish what is observed from what is inferred (§19, §36). Silently turning a
correlation into a fact is the core failure mode this project exists to prevent.

## Options considered

1. **No tiering** — everything is "data"; inferences masquerade as facts. Rejected.
2. **UI-only labels** — cosmetic; the store still allows promotion and loses the distinction on
   export.
3. **Semantic tier as a first-class, enforced attribute** on every claim, with promotion gated by an
   audited human action.

## Decision

Adopt option 3. Every claim-bearing record carries `semantic_tier ∈ {FACT, INTELLIGENCE,
CORRELATION, CONCLUSION}` (and ATTRIBUTION as an approved-correlation state). The application
**forbids auto-promotion**: `CORRELATION → FACT/CONCLUSION` requires an explicit, attributed,
audited human decision. Conclusions must be explainable, evidence-backed, attributable to a named
analyst, and audited.

Example: `FACT: IP observed` → `INTELLIGENCE: IP belongs to ISP X` → `CORRELATION: IP+identifier+time
↔ Entity Y (92%)` → `CONCLUSION: analyst assesses association`.

## Consequences

- Inference can never be mistaken for fact, in store, UI, or export (tests #5).
- Reporting distinguishes tiers explicitly; confidence travels with every non-FACT claim.
- Requires promotion workflows and analyst attribution — deliberate friction.
