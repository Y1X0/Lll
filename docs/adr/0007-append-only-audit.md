# ADR-0007 — Append-only, hash-chained audit + WORM anchoring

- **Status:** Proposed
- **Date:** 2026-08-11
- **Deciders:** Architecture review (pending)

## Context

The audit log must not be an ordinary editable table. It must be append-only and tamper-evident, and
there must be a verifiable `PASS/FAIL` integrity operation. Audit underpins the legal defensibility
of everything else, so it is built in Phase 1 before feature work depends on it.

## Options considered

1. **Plain audit table.** Editable rows; an insider or a DB compromise can alter or delete history
   undetectably. Rejected.
2. **Append-only table (revoked UPDATE/DELETE) only.** Prevents casual edits but a privileged
   compromise can still tamper; no cryptographic tamper-evidence.
3. **Append-only + cryptographic hash chain + monotonic seq + signed checkpoints + WORM export.**
   Each event chains to its predecessor by hash; altering/removing any event breaks the chain from
   that point; `seq` detects gaps/reordering independently; periodic signed checkpoints allow fast
   verification and external anchoring; WORM export preserves an immutable copy.

## Decision

Adopt option 3:

- **Append-only store**: UPDATE/DELETE grants revoked on `audit_events`.
- **Hash chain**: `event_hash = H(canonical(event) || prev_event_hash)`.
- **Monotonic `seq`**: unique, gap-checked, independent of the hash chain.
- **Checkpoints**: `audit_integrity_records` store `{from_seq, to_seq, chain_head_hash, signature,
  anchor_location}` periodically; anchored to WORM storage.
- **Transactional writes**: security-relevant actions emit their audit event in the same transaction
  as the action (no best-effort logging for security events).
- **Verification**: `VERIFY AUDIT INTEGRITY` recomputes the chain from the last trusted checkpoint,
  checks `seq` continuity, compares to the signed head → PASS/FAIL (reporting the first divergent
  `seq`); the verification run is itself audited.

## Consequences

- Tamper-evidence against insiders and DB compromise (Threat Model T9).
- Slight write overhead (hash computation, canonicalization) — acceptable for audit volumes.
- Requires WORM-capable storage or application-layer emulation for anchoring (Open Question).
- The same hash-chain pattern is reused for the custody event stream (ADR-0006).
