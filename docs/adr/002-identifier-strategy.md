# ADR-002 — Identifier strategy (UUIDv7 / ULID / UUIDv5)

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

The brief prohibits Python's `hash()` for IDs (NFR-1, §26). IDs must be stable, collision-resistant,
DB-safe, globally unique, and reproducible where required. `hash()` is process-seeded (randomized
per run for `str`/`bytes`), not collision-resistant, and not stable across processes/runtimes/
versions — disqualifying for durable identifiers.

## Options considered

1. **UUIDv4** — unique, collision-resistant, but random ordering hurts index locality on
   telemetry/audit.
2. **UUIDv7** — time-ordered + random → unique, collision-resistant, **index-friendly**, native
   `uuid`.
3. **ULID** — lexicographically sortable, URL-safe, non-enumerable — ideal for opaque public tokens
   (tracking links).
4. **UUIDv5** — namespace + name → reproducible; for cases where identical input must yield the same
   ID (deterministic derivations, dedup keys) via cryptographically stable canonicalization.

## Decision

- **Primary keys:** **UUIDv7**.
- **Opaque public tokens** (tracking links, external-facing IDs): **ULID**.
- **Deterministic/reproducible IDs** ("reproducible where required"): **UUIDv5** over a fixed,
  governed namespace, computed on a **canonicalized** input.
- **Human-facing IDs** (case/evidence numbers): separate, human-readable, unique columns — never PKs.
- **`hash()` and non-cryptographic/process-seeded schemes are prohibited.**

## Consequences

- Time-ordered PKs improve insert/range-scan performance on high-volume tables.
- Three ID types add minor conceptual overhead, each with a documented use.
- Deterministic IDs fix their namespace + canonicalization + digest to remain reproducible; these
  become governed constants.
