# DILIP — Architecture Documentation

**Digital Investigation & Linked Intelligence Platform** — Discovery / Architecture phase.

> **Status: Phase 0 (Discovery). No production code.** These documents are a proposal awaiting
> architecture review and approval. Per the engineering brief, no implementation (code, migrations,
> Dockerfiles, APIs, schema changes, deployments, real integrations) begins until the architecture
> is approved.

## Contents

| Document | Purpose |
|---|---|
| [DILIP-TECHNICAL-PROPOSAL.md](./DILIP-TECHNICAL-PROPOSAL.md) | **Primary deliverable** — the full 20-section Technical Proposal. |
| [adr/](./adr/) | Architecture Decision Record index and skeletons. |
| [architecture/threat-model.md](./architecture/threat-model.md) | Standalone threat model (expanded from Proposal §13). |
| [architecture/data-model.md](./architecture/data-model.md) | Logical data model / ERD (expanded from Proposal §6). |

## The governing principle

DILIP is a **Digital Investigation Evidence & Intelligence Platform**, not a tracking tool. A
tracking link is one collection mechanism inside a larger accountable pipeline:

```
Collection → Provenance → Enrichment → Correlation → Human Review → Evidence → Audit → Report
```

The semantic ladder is never short-circuited:

```
Observed Data → Enriched Data → Correlation → Attribution
```

- A tracking link ≠ a phone number.
- An IP address ≠ a person.
- A geolocation ≠ a person's location with certainty.

For every result the system must answer: where did it come from, when was it collected, by what
method, under what authority, who accessed it, has it changed, what is our confidence, how does it
link to other evidence, and who approved it. If those questions cannot be answered, the data is not
legal-grade evidence.

## Review

The Technical Proposal is submitted for review. Feedback and approval decisions should be recorded
against the relevant ADRs before Phase 1 (Foundation) begins.
