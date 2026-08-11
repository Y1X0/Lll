# ADR-0010 — Single Authorized Integration Gateway

- **Status:** Proposed
- **Date:** 2026-08-11
- **Deciders:** Architecture review (pending)

## Context

DILIP contacts sensitive external systems (IP intelligence, OSINT sources, and — where lawfully
authorized — telecom/network correlation providers). If external calls are scattered across modules,
the security surface, auditability, and data-minimization guarantees fragment. The brief also draws
a hard boundary: DILIP must never become an interception/intrusion platform; it only *receives*
authorized results.

## Options considered

1. **Direct external calls from each module.** Simple but uncontrolled: inconsistent auth, no central
   audit, no purpose binding, and any compromised module can reach external systems and the DB.
2. **A shared HTTP client library.** Centralizes some code but not the trust boundary; modules still
   hold credentials and can egress freely.
3. **A single Authorized Integration Gateway** as the only egress path, isolated in its own network
   segment, with a connector registry and per-connector controls.

## Decision

Adopt option 3. All sensitive external contact routes through one gateway:

```
DILIP Core → Authorized Integration Gateway → Approved External System
           → Authorized Result → DILIP Correlation/Intelligence Engine
```

Per-connector controls: authentication (mTLS where appropriate), authorization, **purpose binding**,
schema validation, request/response logging (metadata), timeout, retry, rate limiting, **data
minimization**, data classification, response provenance, **legal authorization reference**, and
failure isolation.

Hard constraints:
- The gateway **cannot** directly access the full DILIP database; it exchanges typed requests/results
  with core modules only.
- Raw external payloads are stored **only** when required and authorized; otherwise only minimized
  results + provenance are retained.
- DILIP performs **no** interception or network intrusion; it consumes authorized results.

## Consequences

- One choke point to secure, audit, rate-limit, and isolate (Threat Model T4).
- Enables air-gapped/private-cloud egress control (only the gateway segment may reach out).
- Adds an internal hop and a connector-registry abstraction; justified by the security and legal
  boundary requirements.
- Later extraction of the gateway into a standalone service is straightforward (module boundary
  already enforced — ADR-0002).
