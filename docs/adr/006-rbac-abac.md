# ADR-006 — RBAC + ABAC + case/tenant isolation

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

Roles alone are insufficient (SEC-2/3). An Investigator on Case A must not reach Case B by default;
sensitive fields depend on classification/clearance; multi-tenant deployments need org isolation.

## Options considered

1. **RBAC only** — coarse; cannot express case membership, classification, or tenant scoping;
   invites IDOR/cross-case access.
2. **RBAC + case-level checks in handlers** — better, but scattered checks are easy to miss and hard
   to test.
3. **Single Policy Decision Point layering RBAC + case-level + ABAC/classification + tenant + legal
   boundary, enforced at the query layer (row-level security)** — every access is scoped centrally.

## Decision

Adopt option 3. A single policy decision point every module consults, combining: **RBAC** (roles →
permission codes); **case-level** (membership via `case_members`); **ABAC/classification**
(attributes, clearance vs data classification); **tenant** (`organizations`); **legal-authorization
boundary** (valid authorization covering the action). Isolation is enforced at the query layer via
PostgreSQL **row-level security** + scoped repositories, not only in handlers. Cross-case access is a
monitored, audited exception path.

## Consequences

- Prevents cross-case/cross-tenant access (test #3) and IDOR by construction.
- Requires a well-tested policy engine and RLS policies; central point simplifies audit and testing.
- Roles: Investigator, Supervisor, Auditor, Evidence Viewer (+ Admin), with evidence/audit
  immutability independent of role.
