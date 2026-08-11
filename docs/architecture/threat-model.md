# DILIP — Threat Model (Phase 0 baseline)

Expanded from [Technical Proposal §14](../DILIP-TECHNICAL-PROPOSAL.md#14-threat-model). Discovery-
phase baseline; a per-module STRIDE pass with data-flow diagrams is a Phase-1 entry task. Each
threat is rated across Impact / Likelihood / Attack Surface, with Mitigation, Residual Risk,
Detection, and Response.

## 1. Assets

| Asset | Why it matters | Primary controls |
|---|---|---|
| Evidence artifacts & integrity | Legal admissibility | Content-addressed WORM, multi-hash, signed manifests (ADR-003) |
| Chain of custody | Defensible history | Append-only hash-linked stream (ADR-004) |
| Audit trail | Accountability | Append-only hash chain + signed WORM anchor (ADR-005) |
| Identifiers, phone & correlation data | Rights impact, sensitivity | Column encryption, ABAC, human review (ADR-006/009/011) |
| Legal authorizations | Lawfulness of collection | Purpose binding, gateway checks (ADR-008) |
| Secrets / keys | System compromise | KMS, no secrets in source, mTLS (SEC-4) |
| Case/tenant boundaries | Confidentiality, isolation | Row-level security, ABAC (ADR-006) |

## 2. Trust boundaries

1. Browser ↔ API (untrusted client; internet-facing tracking endpoints).
2. API ↔ modules (in-process, typed; policy decision point on every call).
3. Modules ↔ data stores (least-privilege roles; WORM for evidence/audit).
4. Core ↔ Integration Gateway ↔ external systems (only egress; mTLS, purpose binding).
5. App ↔ audit anchor / signing key (key custody outside the app trust boundary).
6. Operator ↔ system (insider/admin; separation of duties, audited access).

## 3. Actors

External attacker · Malicious investigator · Compromised investigator account · Privileged admin ·
Malicious insider · Compromised external integration · Supply-chain adversary · Legitimate oversight
(auditor/court — a design audience, not a threat).

## 4. Abuse cases (STRIDE-tagged, full rating)

| # | STRIDE | Threat | Impact | Likelihood | Attack Surface | Mitigation | Residual | Detection | Response |
|---|---|---|---|---|---|---|---|---|---|
| T1 | I/R | Malicious investigator | High | Med | Authenticated app | Case/tenant scoping, ABAC, per-access audit, supervisor approval | Med | Access anomaly, audit review | Revoke, preserve audit |
| T2 | S | Compromised investigator account | High | Med | Auth surface | MFA, short-lived+revocable tokens, anomaly detection | Med | Impossible-travel alerts | Revoke sessions, re-auth |
| T3 | T/R | Privileged admin abuse | Critical | Low | Admin plane | Separation of duties, revoked UPDATE/DELETE, offline audit anchor, KMS key separation | Med | Chain verify, anchor mismatch | Break-glass review, key custody |
| T4 | I | Database compromise | Critical | Low | DB tier | At-rest+column encryption, KMS, least-privilege roles, segmentation | Med | Integrity verify | Rotate keys, restore, notify |
| T5 | T | Evidence tampering | Critical | Low | Evidence store | Content-addressed WORM, multi-hash, signed manifests, verify op | Low | `VERIFY EVIDENCE` FAIL | Quarantine, restore from WORM |
| T6 | T/R | Audit tampering | Critical | Low | Audit store | Append-only, hash chain, seq gaps, signed WORM anchor | Low | `VERIFY AUDIT` FAIL | Investigate, restore anchor |
| T7 | I | Insider data exfiltration | High | Med | Export/report | Classification-aware export, approval, watermark/sign, export audit, DLP | Med | Export-volume anomaly | Revoke, legal hold |
| T8 | E/T | External integration compromise | High | Low-Med | Gateway | Isolation, mTLS, per-connector scope, no direct DB, schema validation | Low | Connector/schema anomaly | Disable connector, rotate |
| T9 | E | SSRF | High | Med | Tracking destinations | Scheme/HTTPS enforce, allowlist, private-IP block, DNS-rebinding recheck | Low | Blocked-request logs | Block, alert |
| T10 | S | Open redirect | Med | Med | Tracking endpoint | Destination validation, allowlist, normalization, redirect policy | Low | Redirect-decision logs | Disable link, audit |
| T11 | S | Credential theft | High | Med | Auth, secrets | MFA, no secrets in source, KMS, secret scanning, log redaction | Low | Auth anomaly, scan hits | Rotate, revoke |
| T12 | E | Cross-case access | High | Med | AuthZ layer | Row-level case/tenant scoping, ABAC, isolation tests | Low | Denied-access audit | Alert, review authZ |
| T13 | T | Supply-chain compromise | Critical | Low-Med | Deps/build | Pinned deps, SBOM, signed artifacts, vuln scan, offline mirror | Med | SBOM diff, signature check | Rebuild from trusted, roll back |
| T14 | T | Malicious evidence file | High | Med | Ingestion | Sandboxed ingest, type/size validation, no server-side execution, AV scan | Low | Ingest validation logs | Quarantine, hash, review |
| T15 | T | Correlation poisoning | High | Med | Intelligence inputs | Provenance + source-reliability weighting, human review, CONTRADICTS edges, no auto-promotion | Med | Confidence/provenance review | Down-weight source, re-review |

## 5. Priority invariants

The invariants that determine whether output is legal-grade evidence:

1. **Evidence integrity** (T5) — provable byte-level sameness.
2. **Audit integrity** (T6) — tamper-evident even under privileged/partial compromise.
3. **Case/tenant isolation** (T12) — no cross-case access by default.
4. **No unauthorized/over-confident attribution** (T15, INT-4) — inference never auto-promoted.

## 6. Phase-1 follow-up

Per-module STRIDE with data-flow diagrams; abuse-case-driven security test suite mapping T5/T6/T9/
T10/T12/T13 to the seven provable release-gate tests (Proposal §17); key-management and
incident-response runbooks.
