# ADR-015 — Private cloud deployment

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

Where not fully air-gapped, DILIP runs in a private cloud with internal infrastructure (§24). It must
not depend on public managed services that would place sensitive evidence outside the operating
authority's control.

## Options considered

1. **Public managed cloud services** — places evidence/keys with a third party; unacceptable for the
   sensitivity involved. Rejected as the baseline.
2. **Lift-and-shift single VM** — no segmentation, no HA, weak isolation.
3. **Segmented private-cloud topology** with internal-only managed components.

## Decision

Adopt option 3: private networking with **network segmentation** (frontend / API / data / gateway
tiers); internal load balancing; private PostgreSQL (encrypted, PITR); private object storage
(WORM-capable for evidence/audit); internal identity provider; secrets manager/KMS; private
container registry; centralized structured logging, metrics, alerting; backup/DR with tested restore.
The Integration Gateway segment is the only tier permitted to egress to approved external systems.

## Consequences

- Evidence, keys, and audit remain within the operating authority's control.
- Requires internal platform capabilities (IdP, KMS, object storage, registry) — availability is an
  Open Question.
- Shares the same application build as air-gapped mode; deployment differs, not the core.
