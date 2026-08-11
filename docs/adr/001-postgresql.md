# ADR-001 — PostgreSQL as production database

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

The prototype uses SQLite in a single file. DILIP is a multi-user, multi-case, legal-grade evidence
and intelligence platform requiring strong concurrency, referential integrity, encryption at rest,
row-level case/tenant isolation, and point-in-time recovery. Every stored claim must be provably
intact and auditable.

## Options considered

1. **Keep SQLite** — single-writer, weak concurrent writes, no DB-level roles, limited encryption,
   no server-side PITR; awkward for the constraint/enum/`jsonb` richness the model needs.
2. **PostgreSQL** — MVCC concurrency; rich constraints/enums/`jsonb`/partial indexes; encryption at
   rest (volume + column); PITR via WAL archiving; least-privilege roles; **row-level security** for
   case/tenant isolation; mature ops tooling; runs private-cloud and air-gapped.
3. **MySQL/MariaDB or NewSQL** — viable but no advantage here; weaker on `jsonb`, partial indexes,
   RLS, and extension ecosystem.

## Decision

Adopt **PostgreSQL 16+**. SQLite is retained only as a possible local test fixture, never in
production paths.

## Consequences

- Enables append-only/audit, provenance, constraints (Proposal §6, §9) and **row-level security**
  for case/tenant isolation (SEC-2/3, ADR-006).
- Requires migration tooling, pooling, and a backup/PITR + tested-restore process (NFR-4).
- Adds an infrastructure dependency; justified. Prototype demo/mock data is discarded.
