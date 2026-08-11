# ADR-009 — Phone intelligence model (three authorized paths + fusion)

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

Phone-identity intelligence is a core capability, but the platform must **never** assume it can learn
a phone number from a link visit (§8, §36). Any phone signal must arrive through authorized paths
with full provenance, and never auto-become identity.

## Options considered

1. **Direct "phone from telemetry"** — technically false and legally unacceptable. Rejected outright.
2. **One generic external phone lookup** — hides provenance and conflates very different source types
   and authorizations.
3. **Three separate authorized paths + a fusion layer** — (1) authorized call/communication records,
   (2) authorized OSINT, (3) authorized telecom/signaling — each with distinct provenance,
   authorization, and stated capability limits; fused only into *candidates* for human review.

## Decision

Adopt option 3. Store observed identifiers with source + authorization + timestamp + evidence; the
Correlation Engine builds **candidate** relationships with confidence; a fusion layer combines the
three paths into identity candidates → **human review** → finding. **Confidence ≠ Fact**; no
automatic `CORRELATION → FACT`. Telecom infrastructure never connects to the core app — results
arrive via the Integration Gateway (ADR-008). Each path documents CAN / CANNOT establish (Proposal
§10). OSINT is stored as INTELLIGENCE, never FACT, absent corroboration + review.

## Consequences

- Legally defensible, provenance-preserving phone intelligence; conflicts surfaced (INT-5).
- More modelling effort than a naive lookup; this is the point of the platform.
- DILIP stays a consumer of authorized results, never an interception tool (§37).
