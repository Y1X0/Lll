import unittest
from mfaf.timeline import Timeline
from mfaf.errors import ValidationError
from mfaf.tests._helpers import fresh_db, seed_case, cleanup


class TestTimeline(unittest.TestCase):
    def setUp(self):
        self.db, self.d = fresh_db()
        seed_case(self.db)
        self.tl = Timeline(self.db)

    def tearDown(self):
        cleanup(self.db, self.d)

    def test_chronological_ordering(self):
        self.tl.add("CASE-T", "DEVICE_CONNECTED", timestamp="2026-01-01T10:00:00+00:00")
        self.tl.add("CASE-T", "REBOOT", timestamp="2026-01-01T09:00:00+00:00")
        self.tl.add("CASE-T", "EVIDENCE_CREATED", timestamp="2026-01-01T11:00:00+00:00")
        order = [e["event_type"] for e in self.tl.chronological("CASE-T")]
        self.assertEqual(order, ["REBOOT", "DEVICE_CONNECTED", "EVIDENCE_CREATED"])

    def test_unknown_event_type_rejected(self):
        with self.assertRaises(ValidationError):
            self.tl.add("CASE-T", "MAGIC")

    def test_confidence_and_metadata_roundtrip(self):
        self.tl.add("CASE-T", "AUTHENTICATION_ATTEMPT", metadata={"attempt": 3},
                    confidence="INFERRED")
        ev = self.tl.chronological("CASE-T")[0]
        self.assertEqual(ev["metadata"]["attempt"], 3)
        self.assertEqual(ev["confidence"], "INFERRED")


if __name__ == "__main__":
    unittest.main()
