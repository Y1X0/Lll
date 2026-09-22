import json, os, unittest
from mfaf import models as M
from mfaf.acquisition import AcquisitionEngine, MockAcquisitionProvider, UnavailableAcquisitionProvider
from mfaf.custody import CustodyLog
from mfaf.timeline import Timeline
from mfaf.mock_device import MockMobileDevice, MockDeviceConfig
from mfaf.auth_harness import AuthenticationHarness
from mfaf.report import ReportGenerator
from mfaf.tests._helpers import fresh_db, seed_case, cleanup


class TestReport(unittest.TestCase):
    def setUp(self):
        self.db, self.d = fresh_db()
        seed_case(self.db)
        self.cust = CustodyLog(self.db); self.tl = Timeline(self.db)

    def tearDown(self):
        cleanup(self.db, self.d)

    def _populate(self):
        eng = AcquisitionEngine(self.db, self.cust, self.tl)
        eng.run("CASE-T", "dev1", MockAcquisitionProvider(), None, os.path.join(self.d, "s"), "ex1")
        eng.run("CASE-T", "dev1", UnavailableAcquisitionProvider("locked"), None,
                os.path.join(self.d, "s2"), "ex1")
        dev = MockMobileDevice(MockDeviceConfig(rate_limit_after=3, lockout_after=5)); dev.connect()
        self.db.add_experiment(M.Experiment("EXP-1", "CASE-T", dev.target_id, "EXP-006", "lockout"))
        AuthenticationHarness(self.db, self.cust).run_experiment(
            "EXP-1", dev, [f"w{i}" for i in range(6)])

    def test_report_json_has_16_sections(self):
        self._populate()
        d = ReportGenerator(self.db).collect("CASE-T")
        self.assertEqual(len(d["sections"]), 16)
        self.assertTrue(d["metrics"]["chain_of_custody_valid"])

    def test_report_distinguishes_fact_interpretation_limitation(self):
        self._populate()
        findings = ReportGenerator(self.db).collect("CASE-T")["sections"]["13_findings"]
        types = {f["type"] for f in findings}
        self.assertIn("OBSERVED_FACT", types)
        self.assertIn("LIMITATION", types)

    def test_report_states_acquisition_not_available(self):
        self._populate()
        d = ReportGenerator(self.db).collect("CASE-T")
        statuses = [a["status"] for a in d["sections"]["6_acquisition_results"]]
        self.assertIn("NOT_AVAILABLE", statuses)

    def test_markdown_renders(self):
        self._populate()
        md = ReportGenerator(self.db).render_markdown("CASE-T")
        self.assertIn("# MFAF — Forensic Report", md)
        self.assertIn("Chain of Custody", md)

    def test_no_unlock_claim_without_evidence(self):
        self._populate()
        js = ReportGenerator(self.db).render_json("CASE-T").lower()
        self.assertNotIn("device compromised", js)
        self.assertNotIn("unlocked the device", js)


if __name__ == "__main__":
    unittest.main()
