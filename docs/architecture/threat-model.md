# DILIP — Threat Model (Phase 0 baseline)

Expanded from [Technical Proposal §13](../DILIP-TECHNICAL-PROPOSAL.md#13-threat-model). This is a
discovery-phase baseline; a per-module STRIDE pass is a Phase-1 entry task.

## 1. Assets to protect

| Asset | Why it matters | Primary controls |
|---|---|---|
| Evidence artifacts & their integrity | Legal admissibility | Content-addressed WORM, multi-hash, signed manifests (ADR-0006) |
| Audit trail | Accountability & defensibility | Append-only hash chain, WORM anchor (ADR-0007) |
| Subject identifiers & correlation results | Rights impact, sensitivity | Column encryption, need-to-know, human review |
| Authorization references / legal basis | Lawfulness of collection | Purpose binding, gateway checks |
| Credentials / secrets / keys | System compromise | KMS, no secrets in source, mTLS |
| Telemetry & provenance | Chain from observation to conclusion | Provenance envelope, semantic tiers |

## 2. Trust boundaries

1. **Browser ↔ API** (untrusted client input; tracking endpoints are internet-facing).
2. **API ↔ modules** (in-process, typed; authZ decision point on every call).
3. **Modules ↔ data stores** (least-privilege DB roles; WORM stores for evidence/audit).
4. **Core ↔ Integration Gateway ↔ external systems** (the only egress; mTLS, purpose binding).
5. **Operator ↔ system** (insider threat; need-to-know, audit of every access).

## 3. Actors

- **External attacker** — no credentials; targets internet-facing endpoints and dependencies.
- **Malicious insider** — valid credentials; abuses legitimate access.
- **Compromised investigator account** — attacker with a valid user's session.
- **Compromised integration/connector** — a subverted external system or connector credential.
- **Legitimate oversight** (court/auditor) — a *design audience*, not a threat: the system must
  satisfy their scrutiny.

## 4. Abuse cases (STRIDE-tagged)

| # | STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|---|
| T1 | S/E | API breach via weak authN/authZ | TLS, MFA-ready authN, layered authZ, rate limiting | Low–Med |
| T2 | I | Insider data exfiltration | Need-to-know, classification, per-access audit, egress DLP | Med |
| T3 | S | Stolen investigator session | Short-lived tokens + revocation, MFA, anomaly detection, supervisor gates | Med |
| T4 | E/T | Compromised connector reaches DB/other data | Gateway isolation, no direct DB access, per-connector scope, mTLS | Low |
| T5 | T | Injection / XSS | Parameterized queries, Pydantic validation, output encoding, CSP | Low |
| T6 | E | SSRF / open redirect via tracking destination | Scheme/HTTPS enforcement, allowlist, private-IP block, DNS-rebinding re-check | Low |
| T7 | I | Database compromise reveals sensitive fields | At-rest + column encryption, KMS key separation, least-privilege roles | Med |
| T8 | T | Evidence tampering | Content-addressed WORM, multi-hash, signed manifests, verify op | Low |
| T9 | T/R | Audit tampering or repudiation | Append-only, hash chain, seq gaps, signed checkpoints, WORM | Low |
| T10 | I | Exfiltration via report/export | Classification-aware export, approval, signing/watermark, export audit | Med |
| T11 | — | Unauthorized / over-confident attribution | Mandatory human review, semantic tiers, authorization boundary, purpose binding | Med |
| T12 | I | Secret leakage (source/logs) | No secrets in source, CI secret scanning, log redaction, KMS | Low |
| T13 | — | Air-gap violation (external fetch) | Vendored deps, strict CSP, egress only via gateway | Low |

## 5. Priority invariants

The three invariants that determine whether output is legal-grade evidence:

1. **Evidence integrity** (T8) — provable byte-level sameness.
2. **Audit integrity** (T9) — tamper-evident, verifiable history.
3. **No unauthorized/over-attribution** (T11) — inference is never auto-promoted to fact; attribution
   requires authorized, reviewed correlation.

## 6. Follow-up (Phase 1)

- Per-module STRIDE decomposition with data-flow diagrams.
- Abuse-case-driven security test suite (maps T5, T6, T8, T9 to release-gate tests — Proposal §16).
- Key-management and incident-response runbooks.
