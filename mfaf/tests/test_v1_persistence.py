import json, os, unittest
from mfaf.v1_import import import_v1
from mfaf.timeline import Timeline
from mfaf.report import ReportGenerator
from mfaf.tests._helpers import fresh_db, seed_case, cleanup


def _doc(status="IN_PROGRESS", **over):
    d = {
        "validation_version": "V1", "status": status,
        "examiner": {"examiner_id": "ex1"}, "case": {"case_id": "CASE-P"},
        "device": {"device_id": "pixel", "model": "Pixel", "serial": None},
        "environment": {"mfaf_commit": "local"},
        "observations": [{"timestamp": "2026-01-01T10:00:00+00:00",
                          "observation": "device locked at baseline", "type": "BASELINE"}],
        "acquisitions": [{"provider": "android", "status": "NOT_AVAILABLE",
                          "reason": "locked, no authorized path"}],
        "evidence": [], "timeline": [
            {"event_type": "USB_CONNECTED", "timestamp": "2026-01-01T10:00:00+00:00"}],
        "integrity_checks": [], "limitations": ["screen locked"], "raw_logs": [],
        "metrics": {"usb_observation_success": True,
                    "authorized_acquisition_available": False,
                    "evidence_hash_verified": None},
        "notes": "field note from examiner",
    }
    d.update(over)
    return d


class TestV1Persistence(unittest.TestCase):
    def setUp(self):
        self.db, self.d = fresh_db()
        seed_case(self.db, case="CASE-P")
        self.tl = Timeline(self.db)

    def tearDown(self):
        cleanup(self.db, self.d)

    def _import(self, doc):
        p = os.path.join(self.d, "v1.json")
        json.dump(doc, open(p, "w"))
        return import_v1(self.db, p, "CASE-P", timeline=self.tl)

    # A — persistence
    def test_A_valid_import_creates_one_row(self):
        self._import(_doc())
        self.assertEqual(self.db.count_v1_imports("CASE-P"), 1)

    # B — status persists
    def test_B_statuses_persist(self):
        self._import(_doc(status="PARTIAL"))
        row = self.db.get_latest_v1_import("CASE-P")
        self.assertEqual(row["declared_status"], "PARTIAL")
        self.assertEqual(row["effective_status"], "PARTIAL")

    # C — observations round-trip
    def test_C_observations_roundtrip(self):
        self._import(_doc())
        row = self.db.get_latest_v1_import("CASE-P")
        self.assertEqual(row["observations"][0]["observation"], "device locked at baseline")

    # D — metrics round-trip (null stays null)
    def test_D_metrics_roundtrip(self):
        self._import(_doc())
        row = self.db.get_latest_v1_import("CASE-P")
        self.assertIs(row["metrics"]["evidence_hash_verified"], None)
        self.assertIs(row["metrics"]["usb_observation_success"], True)

    # E — notes round-trip
    def test_E_notes_roundtrip(self):
        self._import(_doc())
        row = self.db.get_latest_v1_import("CASE-P")
        self.assertEqual(row["notes"], "field note from examiner")

    # F — multiple imports remain separate
    def test_F_multiple_imports_not_destructive(self):
        self._import(_doc(status="IN_PROGRESS"))
        self._import(_doc(status="PARTIAL"))
        self._import(_doc(status="FAILED"))
        rows = self.db.list_v1_imports("CASE-P")
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["declared_status"] for r in rows],
                         ["IN_PROGRESS", "PARTIAL", "FAILED"])

    # G — report uses latest import
    def test_G_report_uses_latest(self):
        self._import(_doc(status="IN_PROGRESS"))
        self._import(_doc(status="PARTIAL"))
        rep = ReportGenerator(self.db).collect("CASE-P")
        v1 = rep["sections"]["4_2_v1_field_validation"]
        self.assertEqual(v1["latest"]["declared_status"], "PARTIAL")
        self.assertEqual(v1["import_count"], 2)

    # H — missing values render NOT RECORDED
    def test_H_missing_values_not_recorded(self):
        # قضية بلا أي استيراد V1
        rep = ReportGenerator(self.db).collect("CASE-P")
        v1 = rep["sections"]["4_2_v1_field_validation"]
        self.assertEqual(v1["latest_status"], "NOT_VERIFIED")
        md = ReportGenerator(self.db).render_markdown("CASE-P")
        self.assertIn("NOT RECORDED", md)

    # M — report contains V1 section with actual values
    def test_M_report_contains_v1_section(self):
        self._import(_doc(status="PARTIAL"))
        md = ReportGenerator(self.db).render_markdown("CASE-P")
        self.assertIn("V1 Physical Android Validation", md)
        self.assertIn("PARTIAL", md)
        self.assertIn("device locked at baseline", md)

    # report safety — user text cannot break markdown / inject structure
    def test_report_injection_neutralized(self):
        evil = "evil | col\n## FAKE HEADING\n| PASS | PASS |"
        self._import(_doc(notes=evil, observations=[
            {"observation": "x | y ## H", "type": "BASELINE"}]))
        md = ReportGenerator(self.db).render_markdown("CASE-P")
        # لا يجوز أن ينشأ heading مزيّف من نصّ المستخدم
        self.assertNotIn("\n## FAKE HEADING", md)

    # L — V2..V5 isolation unaffected
    def test_L_synthetic_isolation(self):
        from mfaf import validate
        self._import(_doc())
        self.assertTrue(validate.v2_evidence_integrity()["passed"])
        self.assertTrue(validate.v5_report_completeness()["passed"])


if __name__ == "__main__":
    unittest.main()
