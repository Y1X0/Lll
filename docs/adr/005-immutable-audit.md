# ADR-005 — Immutable, tamper-evident audit (hash chain + signed WORM anchor)

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

The audit log must be append-only and tamper-evident, with a verifiable PASS/FAIL integrity op, and
must resist even a **privileged admin** and a **partial application-layer compromise** (§18, §29
T3). "An editable table we call immutable" is not accepted. Audit underpins legal defensibility, so
it is built in Phase 1.

## Options considered

1. **Plain audit table** — editable; insider or DB compromise alters history undetectably. Rejected.
2. **Append-only table only** (revoked UPDATE/DELETE) — stops casual edits; a privileged compromise
   can still tamper; no cryptographic evidence.
3. **Append-only + hash chain + monotonic seq + signed checkpoints + external/WORM anchoring** —
   each event chains by hash; `seq` detects gaps/reordering; periodic signed checkpoints anchored
   outside the app trust boundary make tampering *detectable* even under partial app compromise.

## Decision

Adopt option 3. `audit_events` append-only (UPDATE/DELETE revoked at DB-role level);
`event_hash = H(canonical(event) || prev_event_hash)`; monotonic gap-checked `seq`;
`audit_integrity_records` store signed `{from_seq, to_seq, chain_head_hash, signature,
anchor_location}` checkpoints, anchored to WORM/external storage with the **signing key held
separately (KMS/offline)**. Security-relevant events are written **transactionally** with their
action. `VERIFY AUDIT INTEGRITY` recomputes the chain from the last trusted checkpoint, checks `seq`
continuity, compares to the signed head → PASS/FAIL (first divergent `seq`), and is itself audited.

## Consequences

- Tamper-evidence against insiders, admins, and DB compromise (T3, T6). An ordinary application
  admin cannot delete audit (grants revoked); a deeper compromise is *detected* via anchor/signature
  mismatch because the anchoring key lives outside the app.
- Requires WORM/external anchor and separate key custody (Open Questions).
- Small write overhead — acceptable for audit volumes.
