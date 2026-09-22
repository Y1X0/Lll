import unittest
from mfaf import validate


class TestValidationProtocol(unittest.TestCase):
    def test_v2_integrity_states(self):
        r = validate.v2_evidence_integrity()
        self.assertTrue(r["passed"])
        self.assertEqual(r["results"]["tampered"], "MISMATCH")
        self.assertEqual(r["results"]["removed"], "MISSING")

    def test_v3_tamper_detected(self):
        r = validate.v3_chain_of_custody()
        self.assertTrue(r["passed"])
        self.assertFalse(r["results"]["after_tamper"]["valid"])

    def test_v4_repeatability_deterministic(self):
        r = validate.v4_repeatability(iterations=4)
        self.assertTrue(r["passed"])
        self.assertEqual(r["results"]["unique_result_digests"], 1)

    def test_v5_report_complete(self):
        r = validate.v5_report_completeness()
        self.assertTrue(r["passed"])
        self.assertTrue(all(r["results"]["sections_present"].values()))

    def test_run_all_reports_v1_not_verified(self):
        d = validate.run_all()
        self.assertFalse(d["v1_physical_android"]["executed"])
        self.assertTrue(d["summary"]["all_passed"])


if __name__ == "__main__":
    unittest.main()
