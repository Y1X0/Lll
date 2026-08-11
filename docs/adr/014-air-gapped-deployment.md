# ADR-014 — Air-gapped deployment

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

DILIP must run in an environment fully isolated from the internet (§24). CDN/external dependencies
and online trust anchors are unavailable and would break isolation or create hidden trust in third
parties.

## Options considered

1. **CDN + online dependencies** (prototype approach) — impossible air-gapped; external trust.
   Rejected.
2. **Partial self-hosting** — leftover external calls silently break isolation.
3. **Fully self-contained deployment**: no external CDN/JS/fonts/APIs; self-hosted libraries; offline
   package repository; local fonts/assets/docs; controlled import/export; local trust anchors;
   local signing/timestamp strategy; offline signed updates; SBOM verified on import.

## Decision

Adopt option 3. Frontend is a locally-built static bundle; strict CSP with no external origins. All
dependencies vendored, mirrored, version-pinned; SBOM generated and verified. Internal CA for
TLS/mTLS. Manifest/audit signing uses a **local** signing key and a **local** timestamp/trust anchor
(exact mechanism is an Open Question). The Integration Gateway may be disabled in a fully isolated
enclave; import/export is via signed, verified bundles only.

## Consequences

- True air-gap capability; no hidden external trust.
- Requires an offline mirror, local CA/TSA, and a signed-bundle import/export process.
- Some external intelligence is unavailable while isolated; results are imported under control.
