# Architecture Decision Records (ADRs)

Each ADR captures **context**, **options considered**, **decision**, and **consequences** for one
significant architectural decision. ADRs are proposed in Phase 0 (Discovery) and reviewed/approved
before the corresponding implementation phase. Format: [MADR](https://adr.github.io/madr/)-style.
Status values: `Proposed`, `Accepted`, `Superseded`, `Deprecated`.

## Index

| ADR | Title | Status |
|---|---|---|
| [ADR-001](./001-postgresql.md) | PostgreSQL as production database | Proposed |
| [ADR-002](./002-identifier-strategy.md) | Identifier strategy (UUIDv7 / ULID / UUIDv5) | Proposed |
| [ADR-003](./003-evidence-integrity.md) | Evidence integrity (content-addressed WORM + multi-hash + signed manifests) | Proposed |
| [ADR-004](./004-chain-of-custody.md) | Chain of custody as append-only hash-linked event stream | Proposed |
| [ADR-005](./005-immutable-audit.md) | Immutable, tamper-evident audit (hash chain + signed WORM anchor) | Proposed |
| [ADR-006](./006-rbac-abac.md) | RBAC + ABAC + case/tenant isolation | Proposed |
| [ADR-007](./007-modular-monolith.md) | Modular monolith first | Proposed |
| [ADR-008](./008-integration-gateway.md) | Single Authorized Integration Gateway | Proposed |
| [ADR-009](./009-phone-intelligence-model.md) | Phone intelligence model (3 authorized paths + fusion) | Proposed |
| [ADR-010](./010-geolocation-fusion.md) | Geolocation fusion (3 paths + conflict surfacing) | Proposed |
| [ADR-011](./011-semantic-evidence-tiers.md) | Semantic evidence tiers, no auto-promotion | Proposed |
| [ADR-012](./012-data-classification.md) | Data classification model | Proposed |
| [ADR-013](./013-retention.md) | Retention, legal hold & controlled destruction | Proposed |
| [ADR-014](./014-air-gapped-deployment.md) | Air-gapped deployment | Proposed |
| [ADR-015](./015-private-cloud-deployment.md) | Private cloud deployment | Proposed |

See also the [Technical Proposal §19](../DILIP-TECHNICAL-PROPOSAL.md#19-adr-list).
