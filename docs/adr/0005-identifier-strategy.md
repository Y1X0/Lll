# ADR-0005 — Identifier strategy (UUIDv7 / ULID / UUIDv5)

- **Status:** Proposed
- **Date:** 2026-08-11
- **Deciders:** Architecture review (pending)

## Context

The brief explicitly prohibits Python's `hash()` for IDs. IDs must be stable, collision-resistant,
database-safe, globally unique, and reproducible where required. The prototype's ID approach is
unverified and assumed weak.

Why `hash()` is unacceptable: it is process-seeded (randomized per run via `PYTHONHASHSEED` for
`str`/`bytes`), not collision-resistant, not stable across processes or versions, and not globally
unique — disqualifying it for durable, cross-system identifiers.

## Options considered

1. **Random UUIDv4.** Globally unique, collision-resistant, but random ordering hurts index locality
   for time-series-heavy tables (telemetry, audit).
2. **UUIDv7.** Time-ordered (embedded timestamp) + random component → globally unique, collision-
   resistant, **index-friendly** (monotonic-ish), database-safe as native `uuid`.
3. **ULID.** Lexicographically sortable, URL-safe, compact 26-char text — good for opaque public
   tokens (e.g. tracking-link tokens).
4. **Namespace-based deterministic (UUIDv5).** Reproducible from a namespace + name, for cases where
   the *same input must always yield the same ID* (deterministic derivations, dedup keys).

## Decision

- **Primary keys:** **UUIDv7** (native `uuid`), for global uniqueness + index locality.
- **Opaque public tokens** (tracking links, external-facing identifiers): **ULID** (sortable,
  URL-safe, non-enumerable).
- **Deterministic/reproducible identifiers** (where the brief's "reproducible where required"
  applies, e.g. content dedup, stable derivations): **UUIDv5** over a fixed namespace.
- **Human-facing identifiers** (case numbers, evidence numbers): separate, human-readable, unique
  columns — never used as primary keys.
- **`hash()` and other non-cryptographic/process-seeded schemes are prohibited.**

## Consequences

- Time-ordered PKs improve insert and range-scan performance on high-volume tables.
- Three ID types add minor conceptual overhead; each has a clear, documented use.
- Deterministic IDs must fix their namespace/algorithm to remain reproducible; the namespace becomes
  a governed constant.
