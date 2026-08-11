# ADR-0004 — PostgreSQL over SQLite

- **Status:** Proposed
- **Date:** 2026-08-11
- **Deciders:** Architecture review (pending)

## Context

The prototype uses SQLite embedded in a single Python file. DILIP is a multi-user, legal-grade
evidence and intelligence platform requiring strong concurrency, referential integrity, encryption
at rest, and point-in-time recovery. Every stored claim must be provably intact and auditable.

## Options considered

1. **Keep SQLite.** Zero infra, simple. But single-writer, weak concurrent write handling, no native
   role-based DB access, limited encryption story, no server-side PITR, awkward for the scale of
   constraints (enums, partial indexes, `jsonb`) the model needs.
2. **PostgreSQL.** Mature concurrency (MVCC), rich constraint/enum/`jsonb`/index support, encryption
   at rest (volume + column), PITR via WAL archiving, least-privilege DB roles, wide operational
   tooling; runs in private-cloud and air-gapped deployments.
3. **A different RDBMS (MySQL/MariaDB) or a NewSQL engine.** Viable but no advantage over PostgreSQL
   for this workload and less rich on `jsonb`, partial indexes, and extension ecosystem.

## Decision

Adopt **PostgreSQL 16+** as the relational store. SQLite is retained only as a possible local test
fixture, never in production paths.

## Consequences

- Enables the append-only/audit, provenance, and constraint model in Proposal §6 and §9.
- Requires migration tooling, connection pooling, and a backup/PITR + tested-restore process
  (Proposal §15.4).
- Adds an infrastructure dependency; acceptable given the requirements. Supports both deployment
  modes.
- Prototype data (if any real data exists) needs a one-time migration; demo/mock data is discarded.
