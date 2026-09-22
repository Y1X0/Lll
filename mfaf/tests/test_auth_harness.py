import unittest
from mfaf import models as M
from mfaf.custody import CustodyLog
from mfaf.mock_device import MockMobileDevice, MockDeviceConfig
from mfaf.auth_harness import AuthenticationHarness
from mfaf.tests._helpers import fresh_db, seed_case, cleanup


class TestAuthHarness(unittest.TestCase):
    def setUp(self):
        self.db, self.d = fresh_db()
        seed_case(self.db)
        self.cust = CustodyLog(self.db)
        self.db.add_experiment(M.Experiment("EXP-1", "CASE-T", "mock-target-1",
                                            "EXP-005", "measure"))

    def tearDown(self):
        cleanup(self.db, self.d)

    def test_rate_limit_measurement(self):
        dev = MockMobileDevice(MockDeviceConfig(rate_limit_after=3, lockout_after=99)); dev.connect()
        h = AuthenticationHarness(self.db, self.cust)
        res = h.run_experiment("EXP-1", dev, [f"w{i}" for i in range(5)])
        self.assertTrue(res["metrics"]["rate_limit_detected"])
        # rate_limit_after=3 → المحاولتان 1-2 FAIL ثم المحاولة 3 RATE_LIMITED
        self.assertEqual(res["metrics"]["authentication_failure_count"], 2)
        # الأحداث خُزّنت
        self.assertEqual(len(self.db.list_auth_events("EXP-1")), 5)

    def test_lockout_state_recorded(self):
        dev = MockMobileDevice(MockDeviceConfig(rate_limit_after=3, lockout_after=5)); dev.connect()
        res = AuthenticationHarness(self.db, self.cust).run_experiment(
            "EXP-1", dev, [f"w{i}" for i in range(6)])
        self.assertTrue(res["metrics"]["lockout_detected"])

    def test_reboot_comparison(self):
        dev = MockMobileDevice(MockDeviceConfig()); dev.connect()
        cmp = AuthenticationHarness(self.db).compare_reboot_state(dev, ["w1", "w2"])
        self.assertIn("->", cmp["transition"])
        self.assertIn("before_reboot", cmp)

    def test_custody_event_emitted(self):
        dev = MockMobileDevice(); dev.connect()
        AuthenticationHarness(self.db, self.cust).run_experiment("EXP-1", dev, ["w1"])
        actions = [e["action"] for e in self.cust.list_events(case_id="CASE-T")]
        self.assertIn("EXPERIMENT_RUN", actions)


if __name__ == "__main__":
    unittest.main()
