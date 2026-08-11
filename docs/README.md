# DILIP — Architecture Documentation

**Digital Investigation & Linked Intelligence Platform** — Discovery / Architecture phase.

> **Status: Phase 0 (Discovery). No production code.** These documents are a proposal awaiting
> architecture review and approval. Per the master brief, no implementation (code, migrations,
> Dockerfiles, APIs, real integrations, deployment, infrastructure) begins until Phase 0 is
> approved. See the **Architecture Readiness Verdict** at the end of the proposal.

## Contents

| Document | Purpose |
|---|---|
| [DILIP-TECHNICAL-PROPOSAL.md](./DILIP-TECHNICAL-PROPOSAL.md) | **Primary deliverable** — the full Technical Proposal (24 sections) incl. readiness verdict. |
| [adr/](./adr/) | Architecture Decision Records ADR-001…015. |
| [architecture/threat-model.md](./architecture/threat-model.md) | STRIDE threat model (Impact/Likelihood/Attack-Surface/Mitigation/Residual/Detection/Response). |
| [architecture/data-model.md](./architecture/data-model.md) | Logical data model, ERD, and Entity Graph. |

## The governing principle

DILIP is a **Legal / Compliance-first Digital Investigation & Linked Intelligence Platform**, not a
tracking tool. Every result travels an accountable pipeline:

```
Case → Subjects/Entities → Identifiers → Observations → Intelligence → Evidence
     → Correlation → Analyst Review → Findings → Conclusion → Report
```

The semantic ladder is never short-circuited:

```
Raw Observation → Normalized → Evidence/Intelligence → Correlation → Review → Finding/Conclusion
```

- Tracking Link ≠ Person · Phone ≠ Person · IP ≠ Person · Location ≠ Person · Device ≠ Person
- **Confidence ≠ Fact** — no automatic CORRELATION → FACT.

The platform never says *"we found the phone number / the location."* It says *from which source, at
what time, under which authorization, with what supporting evidence, at what confidence, with which
conflicts, and by which analyst's reviewed steps.* If those questions cannot be answered, the data is
not legal-grade evidence.

## Review

The Technical Proposal is submitted for review. The current **Architecture Readiness Verdict** is
**NOT READY — OPEN QUESTIONS REMAIN**; six blocking questions are listed in §23–§24. Resolve those,
record approval against the relevant ADRs, and Phase 1 (Security Foundation) may begin.
