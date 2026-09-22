import json, os, tempfile, unittest
from mfaf.v1_import import (validate_v1_document, derive_effective_status,
                           import_v1, V1ImportError, V1_STATES)
from mfaf.timeline import Timeline
from mfaf.tests._helpers import fresh_db, seed_case, cleanup

TEMPLATE = "docs/mfaf/v1_android_field_results.template.json"


def base_doc(**over):
    d = {
        "validation_version": "V1", "status": "NOT_VERIFIED",
        "examiner": {}, "case": {}, "device": {}, "environment": {},
        "observations": [], "acquisitions": [], "evidence": [], "timeline": [],
        "integrity_checks": [], "limitations": [], "raw_logs": [],
        "metrics": {},
    }
    d.update(over)
    return d


class TestV1Schema(unittest.TestCase):
    def test_template_is_valid_and_not_verified(self):
        doc = json.load(open(TEMPLATE))
        validate_v1_document(doc)
        self.assertEqual(doc["status"], "NOT_VERIFIED")

    def test_valid_minimal_doc(self):
        self.assertIsNotNone(validate_v1_document(base_doc()))

    def test_missing_required_field_rejected(self):
        d = base_doc(); del d["timeline"]
        with self.assertRaises(V1ImportError):
            validate_v1_document(d)

    def test_wrong_version_rejected(self):
        with self.assertRaises(V1ImportError):
            validate_v1_document(base_doc(validation_version="V2"))

    def test_invalid_status_rejected(self):
        with self.assertRaises(V1ImportError):
            validate_v1_document(base_doc(status="MAGIC"))

    def test_verified_status_rejected(self):
        # لا يُقبل أي status يحمل VERIFIED
        with self.assertRaises(V1ImportError):
            validate_v1_document(base_doc(status="VERIFIED"))

    def test_list_field_must_be_list(self):
        with self.assertRaises(V1ImportError):
            validate_v1_document(base_doc(observations={"x": 1}))

    def test_metric_must_be_tristate(self):
        with self.assertRaises(V1ImportError):
            validate_v1_document(base_doc(metrics={"usb_observation_success": "yes"}))
        # null/true/false مقبولة
        validate_v1_document(base_doc(metrics={"usb_observation_success": None}))
        validate_v1_document(base_doc(metrics={"usb_observation_success": True}))

    def test_null_metric_preserved_not_false(self):
        doc = base_doc(metrics={"evidence_hash_verified": None})
        validate_v1_document(doc)
        self.assertIsNone(doc["metrics"]["evidence_hash_verified"])
        self.assertIsNot(doc["metrics"]["evidence_hash_verified"], False)


class TestV1StatusLogic(unittest.TestCase):
    def test_not_verified_stays_not_verified(self):
        self.assertEqual(derive_effective_status(base_doc(status="NOT_VERIFIED")),
                         "NOT_VERIFIED")

    def test_completed_without_observations_downgraded(self):
        # ادّعاء COMPLETED بلا ملاحظات/قياس → PARTIAL (لا ترقية آلية)
        self.assertEqual(derive_effective_status(base_doc(status="COMPLETED")), "PARTIAL")

    def test_completed_with_real_data_preserved(self):
        d = base_doc(status="COMPLETED",
                     observations=[{"observation": "baseline"}],
                     metrics={"usb_observation_success": True})
        self.assertEqual(derive_effective_status(d), "COMPLETED")


class TestV1Import(unittest.TestCase):
    def setUp(self):
        self.db, self.d = fresh_db()
        seed_case(self.db, case="CASE-V1")
        self.tl = Timeline(self.db)

    def tearDown(self):
        cleanup(self.db, self.d)

    def _write(self, doc):
        p = os.path.join(self.d, "v1.json")
        json.dump(doc, open(p, "w"))
        return p

    def test_import_requires_existing_case(self):
        from mfaf.errors import NotFoundError
        p = self._write(base_doc())
        with self.assertRaises(NotFoundError):
            import_v1(self.db, p, "NO-SUCH-CASE")

    def test_import_preserves_observations(self):
        obs = [{"timestamp": "t1", "observation": "device locked", "type": "BASELINE"}]
        p = self._write(base_doc(status="IN_PROGRESS", observations=obs))
        rec = import_v1(self.db, p, "CASE-V1", timeline=self.tl)
        self.assertEqual(rec["original_document"]["observations"], obs)
        self.assertEqual(rec["observation_count"], 1)

    def test_import_never_auto_verifies(self):
        p = self._write(base_doc(status="NOT_VERIFIED"))
        rec = import_v1(self.db, p, "CASE-V1", timeline=self.tl)
        self.assertEqual(rec["effective_status"], "NOT_VERIFIED")
        self.assertNotIn("VERIFIED", rec["effective_status"].replace("NOT_VERIFIED", ""))

    def test_import_generates_timeline(self):
        doc = base_doc(status="IN_PROGRESS", timeline=[
            {"event_type": "USB_CONNECTED", "timestamp": "2026-01-01T10:00:00+00:00"},
            {"event_type": "DEVICE_IDENTIFIED", "timestamp": "2026-01-01T10:00:05+00:00"},
            {"event_type": "ACQUISITION_NOT_AVAILABLE", "timestamp": "2026-01-01T10:01:00+00:00"},
        ])
        p = self._write(doc)
        rec = import_v1(self.db, p, "CASE-V1", timeline=self.tl)
        self.assertEqual(rec["timeline_events_created"], 3)
        self.assertEqual(len(self.tl.chronological("CASE-V1")), 3)

    def test_import_rejects_malformed_json(self):
        p = os.path.join(self.d, "bad.json")
        open(p, "w").write("{not valid json")
        with self.assertRaises(V1ImportError):
            import_v1(self.db, p, "CASE-V1")

    def test_import_does_not_touch_synthetic_validation(self):
        # استيراد V1 لا يلمس مجموعات V2..V5 (مستقلّة تمامًا)
        from mfaf import validate
        before = validate.v2_evidence_integrity()["passed"]
        p = self._write(base_doc(status="IN_PROGRESS", observations=[{"o": "x"}]))
        import_v1(self.db, p, "CASE-V1", timeline=self.tl)
        after = validate.v2_evidence_integrity()["passed"]
        self.assertTrue(before and after)


if __name__ == "__main__":
    unittest.main()
