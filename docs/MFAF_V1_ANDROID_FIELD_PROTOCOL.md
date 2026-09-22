# MFAF — V1 Physical Android Field Validation Protocol

**Status of this document:** procedure only. Executing it does **not** confirm the
hypothesis. Results are entered by a human examiner and imported via `mfaf v1 import`.

> ⚖️ **Authorization & safety.** This validation is limited to devices **owned or
> otherwise explicitly authorized** for examination. The procedure MUST NOT include:
> lock-screen bypass, exploit steps, PIN/password cracking, encryption bypass, or any
> security-control circumvention. **If a security control prevents acquisition, record
> the control as an observation** — that is a valid forensic result, not a failure to
> work around.

The AI environment has **no physical hardware**; V1 is executed by the human examiner.
The platform never fabricates hardware results. Initial status is always `NOT_VERIFIED`.

---

## A. Preconditions (record before starting)
- Examiner ID / name / organization
- Case ID + legal authority + **ownership/authorization record**
- Device manufacturer / model
- Android version; **security patch level** if legitimately observable
- USB debugging state (as-found — do not change to enable acquisition unless the
  experiment explicitly requires it and the change is documented)
- Test environment (isolated lab)
- MFAF version + commit hash

## B. Baseline (before connecting USB)
Record: device state, lock state, date/time, Android version, model, battery state
(if relevant), USB/debugging configuration. Add each as an `observations[]` entry with
`type: "BASELINE"`.

## C. USB connection observation
Connect the test device normally. Record: USB connection detected, VID/PID (if exposed),
manufacturer/product (if exposed), connection timestamp, device state, whether an
**authorized debugging relationship** already exists. Do not alter security settings
merely to make acquisition possible unless required **and documented**.
Add a `timeline[]` entry `USB_CONNECTED` and, once identified, `DEVICE_IDENTIFIED`.

## D. Authorized acquisition test
Run **only** acquisition methods already supported by MFAF (mock/filesystem, or an
authorized, documented Android workflow). If acquisition is unavailable in the current
authorized state, record in `acquisitions[]`:
`{"provider":"android","status":"NOT_AVAILABLE","reason":"<exact reason>"}` and a
`timeline[]` `ACQUISITION_NOT_AVAILABLE`. **This is a valid result.**

## E. Evidence integrity (only if legitimately acquired)
For each acquired artifact: compute SHA-256, store acquisition metadata, verify the hash,
document the evidence ID. Record `evidence[]` and `integrity_checks[]`
(`result: VERIFIED|MISMATCH|MISSING|ERROR`).

## F. Timeline
Record in order: `USB_CONNECTED` → `DEVICE_IDENTIFIED` → `ACQUISITION_STARTED` →
`ACQUISITION_COMPLETED` or `ACQUISITION_NOT_AVAILABLE` → `USB_DISCONNECTED`, each with a
real timestamp.

## G. Repeatability
Repeat the **non-destructive** observation/acquisition at least 3 times where practical.
Record `metrics.repeatability_runs` (integer) and `metrics.repeatability_consistent`
(true/false). **Do not perform destructive tests.**

---

## Validation states
`NOT_VERIFIED` → `IN_PROGRESS` → (`COMPLETED` | `PARTIAL` | `FAILED`).
"Protocol executed" ≠ "hypothesis confirmed". The report distinguishes
Protocol execution / Observed result / Interpretation / Limitation. The importer will
downgrade a `COMPLETED` claim to `PARTIAL` if there are no observations/measured metrics,
and rejects any status containing "VERIFIED".

## Research metrics (true / false / null)
`device_identification_success`, `usb_observation_success`,
`authorized_acquisition_available`, `evidence_hash_verified`, `timeline_reconstructed`,
`repeatability_runs` (int), `repeatability_consistent`, `unexpected_behavior`,
plus free-text `limitations`. **`null` means not observed / not applicable / not measured
— never treat null as false.**

---

## Reproducible execution (commands are tested for the import/report steps;
## the physical steps 3–5 are performed by the examiner)

```bash
DB=mfaf.db
# 1) identify examiner
python3 -m mfaf.cli --db $DB examiner add --id ex1 --name "Examiner A" --org "Lab"
# 2) create case (record your real legal authority)
python3 -m mfaf.cli --db $DB case create --id CASE-2026-A1 --title "V1 Android" \
    --examiner ex1 --authority "OWNERSHIP/AUTH-REF"
# 3) prepare test device  ....... (examiner, physical)
# 4) execute V1 protocol A–G ..... (examiner, physical)
# 5) record observations into a copy of the template:
cp docs/mfaf/v1_android_field_results.template.json my_v1_results.json
#    (edit my_v1_results.json with real observations)
# 6) import the completed JSON (schema-validated; never auto-PASS)
python3 -m mfaf.cli --db $DB v1 import --file my_v1_results.json --case CASE-2026-A1
# 7) regenerate the report from actual data
python3 -m mfaf.cli --db $DB report generate --case CASE-2026-A1 --format markdown --out v1_report.md
# 8) verify evidence hashes (if any acquired)
python3 -m mfaf.cli --db $DB evidence verify --id <EVIDENCE_ID>
# 9) inspect timeline
python3 -m mfaf.cli --db $DB timeline show --case CASE-2026-A1
```

## Remaining physical-device requirements
Steps A–G and commands 3–5 require an **owned/authorized Android device** and are
**NOT VERIFIED** in the AI environment. Provide the completed
`my_v1_results.json`; it will be imported and the report regenerated from real data.
