# ADR-007 — Modular monolith first

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

DILIP is enterprise-grade, but "enterprise" does not mean microservices. The domain (evidence,
custody, audit, correlation) is still stabilizing, and cross-cutting integrity/audit consistency is
easiest to guarantee within one transactional boundary.

## Options considered

1. **Microservices from day one** — multiplies the security surface, distributed-transaction and
   audit-consistency problems, and operational cost before the domain is stable. Rejected for Phase
   0–3.
2. **Single unstructured monolith** — ships fast but erodes into an unmaintainable ball of mud;
   cannot later extract services.
3. **Modular monolith** — one deployable, strong internal module boundaries (typed service
   interfaces, module-owned tables), so a module can be extracted to a service later *if a real
   need appears*.

## Decision

Adopt option 3. Modules: identity, cases, tracking, intelligence, correlation, geolocation, phone,
evidence, custody, audit, reporting, integrations, compliance. Boundary rules: no cross-module raw
SQL; all egress via `integrations`; evidence/custody/audit expose no update/delete of integrity
records; every access passes the policy decision point.

## Consequences

- Transactional integrity for evidence/custody/audit is straightforward now.
- Clear seams enable later extraction (e.g. Integration Gateway, Intelligence) without a rewrite.
- Requires discipline (enforced via tests/lint on import boundaries).
- A native graph DB for the entity graph is deferred; the relational edge model suffices initially
  and can be extracted behind the intelligence module's interface if scale demands.
