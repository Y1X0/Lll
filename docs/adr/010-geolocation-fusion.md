# ADR-010 — Geolocation fusion (three paths + conflict surfacing)

- **Status:** Proposed · **Date:** 2026-08-11 · **Deciders:** Architecture review (pending)

## Context

`Location = IP location` is wrong and misleading (§12–15, §36). Location must come from independent
sources with explicit precision limits, and disagreement must never be hidden.

## Options considered

1. **Single source (usually IP)** presented as "location" — misrepresents accuracy. Rejected.
2. **Multiple sources, pick the "best"** — silently discards conflict and provenance.
3. **Three independent paths + a fusion layer that surfaces conflict** — IP geo, Wi-Fi/BSSID, cell/
   tower, each stored with method, accuracy estimate, provider, timestamp, confidence, provenance;
   fusion produces candidate locations + confidence + temporal correlation, and marks
   `CONFLICT DETECTED` when sources disagree, preserving every result.

## Decision

Adopt option 3. Each observation stores `method` (IP_GEOLOCATION / WIFI_BSSID / CELL_TOWER),
`accuracy_estimate`, `provider/source`, `timestamp`, `confidence`, `provenance`, `authorization`.
Results are **Estimated Location**, not GPS exact fixes, unless the source itself provides that
precision. The fusion engine never hides disagreement:

```
IP → Amman   BSSID → Zarqa   Cell → Amman   ⇒   Status: CONFLICT DETECTED (all preserved)
```

Human review precedes any locational finding.

## Consequences

- Honest, defensible geolocation; conflicts are first-class (test #6).
- Requires per-source accuracy/confidence modelling and a fusion algorithm (weights are an Open
  Question tied to approved providers).
- BSSID/cell data must be authorized-source (a browser does not expose BSSID).
