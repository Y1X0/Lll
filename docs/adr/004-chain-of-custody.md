# ADR-004 — Chain of custody as an append-only hash-linked event stream

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

Every evidence item needs a complete, tamper-evident chain of custody (EVID-3) recording
who/what/when/why/from/to/authorization/previous-hash/new-hash. A status string
("Created → Reviewed → Secured") cannot prove the history and cannot detect tampering.

## Options considered

1. **Status field / enum on evidence** — no history, no tamper-evidence. Rejected.
2. **Plain custody table** — records events but editable; an insider can alter history.
3. **Append-only, hash-linked event stream** — each event chains to its predecessor by hash; any
   content or ordering change breaks the link; full history is reconstructable by replay.

## Decision

Adopt option 3. `chain_of_custody_events` is append-only (UPDATE/DELETE grants revoked). Each event
stores actor+role, action, timestamp, reason, from/to, authorization, `previous_hash`, and
`new_hash = H(canonical(event) || previous_hash)`. Actions include COLLECTED, IMPORTED, VERIFIED,
ACCESSED, TRANSFERRED, REVIEWED, REFERENCED_IN_REPORT, ARCHIVED. A verification walk detects the
first divergence.

## Consequences

- Reconstructable, tamper-evident custody (Threat T… evidence tampering; provable test #2).
- Same hash-linking pattern as audit (ADR-005), reused deliberately.
- Slight write overhead (canonicalization + hashing) — acceptable.
