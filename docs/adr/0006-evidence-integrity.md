# ADR-0006 — Content-addressed WORM evidence store + multi-hash + signed manifests

- **Status:** Proposed
- **Date:** 2026-08-11
- **Deciders:** Architecture review (pending)

## Context

Evidence must be legal-grade. The requirement is not "we have a hash" but "we can prove the artifact
displayed now is byte-identical to the artifact collected then." The prototype has no real evidence
vault. Originals must be immutable after ingestion; the full history must be reconstructable.

## Options considered

1. **Row in SQLite/PostgreSQL with a stored SHA-256.** Trivial but a stored hash next to mutable
   bytes proves little; the bytes and the hash can both be altered.
2. **Filesystem/object store keyed by an arbitrary ID + hash column.** Better, but a mismatched byte
   can still resolve to the same key.
3. **Content-addressed store (key = content digest) + WORM + multi-hash + signed manifests +
   timestamping.** The storage key *is* the digest, so altered bytes cannot resolve to the same
   address; WORM prevents overwrite; multi-hash guards against a single algorithm weakening; signed,
   timestamped manifests bind integrity to a time and an authority.

## Decision

Adopt option 3:

- **Content-addressed storage**: `storage_address = SHA-256(bytes)`; the address *is* the digest.
- **WORM semantics**: write-once; the evidence module exposes no update/delete of originals.
- **Multi-algorithm hashing**: SHA-256 always; SHA-512 additionally for high-value evidence.
- **Signed manifests**: per-case and per-export manifests list `{evidence_number, storage_address,
  hashes}` and are cryptographically signed.
- **Timestamping**: manifests carry trusted timestamps (RFC-3161-style) where a trust anchor is
  available (see Open Questions on air-gapped TSA).
- **Verification op**: `VERIFY EVIDENCE` recomputes from stored bytes and compares to
  `evidence_hashes` + signed manifest → PASS/FAIL, itself audited.
- **Chain of custody** is a separate append-only `custody_events` stream (see ADR-0007 pattern),
  not a status string.

## Consequences

- Provable byte-level integrity and a reconstructable custody history (Proposal §8).
- Requires WORM-capable object storage (or application-layer WORM emulation — see Open Questions).
- Deduplication is automatic (identical bytes → identical address).
- Deletion only via governed retention/disposition, and never under legal hold.
