# Architecture Decision Records (ADRs)

Each ADR captures **context**, **options considered**, **decision**, and **consequences** for one
significant architectural decision. ADRs are proposed here as part of Phase 0 (Discovery) and are to
be reviewed and approved before the corresponding implementation phase begins.

Format: [MADR](https://adr.github.io/madr/)-style. Status values: `Proposed`, `Accepted`,
`Superseded`, `Deprecated`.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](./0001-modular-monolith.md) | Modular monolith over microservices (first) | Proposed |
| [0002](./0002-module-boundaries.md) | Module boundary & dependency rules | Proposed |
| [0003](./0003-backend-fastapi-python.md) | FastAPI + Python 3.12 backend | Proposed |
| [0004](./0004-postgresql-over-sqlite.md) | PostgreSQL over SQLite | Proposed |
| [0005](./0005-identifier-strategy.md) | Identifier strategy (UUIDv7 / ULID / UUIDv5) | Proposed |
| [0006](./0006-evidence-integrity.md) | Content-addressed WORM evidence store + multi-hash + signed manifests | Proposed |
| [0007](./0007-append-only-audit.md) | Append-only, hash-chained audit + WORM anchoring | Proposed |
| [0008](./0008-frontend-separation.md) | Separate React+Vite frontend, self-hosted (no CDN) | Proposed |
| [0009](./0009-secrets-management.md) | Secrets via env (dev) / KMS (prod) | Proposed |
| [0010](./0010-integration-gateway.md) | Single Authorized Integration Gateway | Proposed |
| [0011](./0011-session-tokens.md) | Short-lived JWT + rotating server-side refresh tokens | Proposed |
| [0012](./0012-provenance-envelope.md) | Provenance envelope as a first-class shared model | Proposed |
| [0013](./0013-semantic-tiers.md) | Semantic tiers with no auto-promotion | Proposed |
| [0014](./0014-human-review-attribution.md) | Mandatory human review before attribution | Proposed |
| [0015](./0015-classification-retention.md) | Data classification & retention model | Proposed |

> Full skeletons are provided for the five most consequential decisions (0004, 0005, 0006, 0007,
> 0010). The remainder are listed here with their decision summary in the
> [Technical Proposal §18](../DILIP-TECHNICAL-PROPOSAL.md#18-adr-list) and will be expanded during
> review.
