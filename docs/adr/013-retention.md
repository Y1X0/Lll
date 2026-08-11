# ADR-013 — Retention, legal hold & controlled destruction

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

Evidence and investigative data must not be deleted by an ad-hoc Delete (§33, COMP-4). Retention must
be policy-driven, legal holds must override disposition, and destruction must itself be evidenced and
audited.

## Options considered

1. **Manual/ad-hoc deletion** — unsafe, unauditable, legally hazardous. Rejected.
2. **Time-based auto-delete only** — ignores legal holds and destruction evidence.
3. **Policy-driven retention + legal hold override + controlled destruction with destruction
   evidence**, all audited.

## Decision

Adopt option 3. `retention_policies` (period + disposition ∈ {DELETE, ANONYMIZE, REVIEW} + legal
basis), case-specific retention, **legal hold** (blocks disposition/deletion of scoped objects while
active). Disposition runs only after the period, only absent a legal hold, and always writes a
**destruction record** (who/when/authorization/what) that is audited. Evidence has **no** direct
delete path (ADR-003); disposition flows through this governed workflow. Audit is never routinely
deleted and typically has the longest retention.

## Consequences

- Defensible lifecycle; no silent loss of evidence (test: legal-hold blocks disposition).
- Retention windows/legal bases bind to the governing regime (Open Question).
- Destruction produces evidence rather than absence.
