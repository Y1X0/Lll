import unittest
from mfaf.mock_device import MockMobileDevice, MockDeviceConfig
from mfaf.errors import SafetyBoundaryError, ValidationError


class TestMockDevice(unittest.TestCase):
    def setUp(self):
        self.dev = MockMobileDevice(MockDeviceConfig(rate_limit_after=3, lockout_after=5,
                                                     lockout_recovery_steps=2))

    def test_locked_to_unlocked_on_correct(self):
        self.dev.connect()
        self.assertEqual(self.dev.get_state()["state"], "LOCKED")
        r = self.dev.submit_controlled_test_attempt("SYNTH-CORRECT")
        self.assertEqual(r["result"], "SUCCESS")
        self.assertEqual(self.dev.get_state()["state"], "UNLOCKED")

    def test_disconnected_rejected(self):
        with self.assertRaises(SafetyBoundaryError):
            self.dev.submit_controlled_test_attempt("x")

    def test_empty_input_rejected(self):
        self.dev.connect()
        with self.assertRaises(ValidationError):
            self.dev.submit_controlled_test_attempt("")

    def test_rate_limit_increases_delay(self):
        self.dev.connect()
        delays = [self.dev.submit_controlled_test_attempt(f"w{i}")["response_time_ms"]
                  for i in range(4)]
        self.assertTrue(self.dev.get_state()["rate_limited"])
        self.assertGreater(delays[-1], delays[0])   # التأخّر يزداد

    def test_lockout_reached_and_not_bypassable(self):
        self.dev.connect()
        for i in range(5):
            self.dev.submit_controlled_test_attempt(f"w{i}")
        self.assertEqual(self.dev.get_state()["state"], "LOCKOUT")
        # حتى المدخل الصحيح لا "يتجاوز" الإغلاق
        r = self.dev.submit_controlled_test_attempt("SYNTH-CORRECT")
        self.assertEqual(r["result"], "LOCKED_OUT")

    def test_recovery_steps(self):
        self.dev.connect()
        for i in range(5):
            self.dev.submit_controlled_test_attempt(f"w{i}")
        self.dev.recover_step(); self.dev.recover_step()
        self.assertIn(self.dev.get_state()["state"], ("RECOVERY", "LOCKED"))

    def test_reboot_keeps_locked_by_default(self):
        self.dev.connect()
        self.dev.submit_controlled_test_attempt("SYNTH-CORRECT")   # UNLOCKED
        self.dev.reboot()
        self.assertEqual(self.dev.get_state()["state"], "LOCKED")  # آمن: يعود مقفلًا

    def test_reboot_clears_attempts_when_configured(self):
        dev = MockMobileDevice(MockDeviceConfig(reboot_clears_attempts=True))
        dev.connect()
        for i in range(2):
            dev.submit_controlled_test_attempt(f"w{i}")
        dev.reboot()
        self.assertEqual(dev.get_state()["failed_attempts"], 0)

    def test_deterministic_repeatable(self):
        def run():
            d = MockMobileDevice(MockDeviceConfig()); d.connect()
            return [d.submit_controlled_test_attempt(f"w{i}")["response_time_ms"] for i in range(6)]
        self.assertEqual(run(), run())


if __name__ == "__main__":
    unittest.main()
