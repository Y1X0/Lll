# ADR-003 — Evidence integrity (content-addressed WORM + multi-hash + signed manifests)

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

Evidence must be legal-grade (EVID-1…4). The requirement is not "we have a hash" but "we can prove
the artifact displayed now is byte-identical to the artifact collected then." The prototype has no
real vault. Originals must be immutable after ingestion; history must be reconstructable.

## Options considered

1. **Row + stored SHA-256** — a hash next to mutable bytes proves little; both can be altered.
2. **Object store keyed by arbitrary ID + hash column** — better, but altered bytes can still map to
   the same key.
3. **Content-addressed store (key = digest) + WORM + multi-hash + signed, timestamped manifests +
   verification op** — the key *is* the digest, so altered bytes cannot resolve to the same address;
   WORM blocks overwrite; multi-hash guards algorithm weakening; signed timestamped manifests bind
   integrity to a time and authority.

## Decision

Adopt option 3: `storage_address = SHA-256(bytes)` (SHA-512 additionally for high-value); WORM
storage; encryption at rest and in transit; per-case and per-export **signed manifests**;
**timestamping** where a trust anchor exists (Open Question in air-gapped mode); `VERIFY EVIDENCE`
op (recompute → compare → PASS/FAIL, audited). No update/delete path for originals; disposition only
via governed retention (ADR-013), never under legal hold.

## Consequences

- Provable byte-level integrity; automatic dedupe (identical bytes → identical address).
- Requires WORM-capable storage or application-layer WORM emulation (Open Question).
- Custody is a separate append-only stream (ADR-004).
