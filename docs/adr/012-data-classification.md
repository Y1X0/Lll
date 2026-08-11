# ADR-012 — Data classification model

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

Sensitivity varies widely (public OSINT vs authorized telecom results). Access, encryption, export,
retention, audit, and reporting must all derive from a consistent classification (COMP-3, §32).

## Options considered

1. **No classification** — uniform handling over- or under-protects data. Rejected.
2. **Free-text sensitivity labels** — inconsistent, unenforceable.
3. **Fixed classification enum bound to handling policies** across access/encryption/export/
   retention/audit/reporting.

## Decision

Adopt option 3: `PUBLIC · INTERNAL · CONFIDENTIAL · RESTRICTED · HIGHLY_RESTRICTED`. Every data
object declares its class. Bindings: **access** (clearance vs class via ABAC, ADR-006);
**encryption** (column encryption for RESTRICTED+); **export** (classification-aware, approval-gated
for higher tiers); **retention** (per-class defaults, ADR-013); **audit** (higher tiers → longer/
stricter); **reporting** (redaction/marking by class). Actual level definitions bind to the
governing regime (Open Question).

## Consequences

- Consistent, enforceable handling driven by one attribute.
- Requires classification at creation for every object; defaults per source/adapter reduce burden.
- Mapping to the operating authority's real scheme is a configuration step, not a redesign.
