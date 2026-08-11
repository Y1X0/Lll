# ADR-008 — Single Authorized Integration Gateway

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

DILIP contacts sensitive external systems (IP-geo, OSINT, telecom/network correlation). Scattered
external calls fragment auditability, data minimization, and the trust boundary. Hard rule (§10,
§22, §37): DILIP must never become an interception/intrusion tool; external systems must never reach
the core DB.

## Options considered

1. **Direct calls per module** — inconsistent auth, no central audit/purpose-binding; a compromised
   module can egress freely and reach the DB. Rejected.
2. **Shared HTTP client library** — centralizes code, not the trust boundary; modules still hold
   credentials.
3. **Single Authorized Integration Gateway** as the only egress, isolated in its own network
   segment, with a connector registry and per-connector controls.

## Decision

Adopt option 3:

```
External System → Integration Gateway → AuthN → AuthZ → Validation → Normalization → Provenance → DILIP
```

Per connector: authentication (mTLS where appropriate), authorization, **purpose binding**, schema
validation, request/response logging (metadata), timeout, retry, rate limiting, **data
minimization**, classification, response provenance, legal authorization reference, failure
isolation. The gateway **cannot** access the full core DB; it exchanges typed requests/results with
modules. Raw external payloads stored only when authorized. **No interception/intrusion** — DILIP
consumes authorized results only.

## Consequences

- One choke point to secure, audit, rate-limit, isolate (T8); enables air-gapped/private-cloud
  egress control (test #7).
- Adds an internal hop + connector registry; justified by security and legal boundaries.
- Straightforward later extraction into a standalone service (ADR-007).
