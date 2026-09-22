import unittest
from mfaf.custody import CustodyLog
from mfaf.errors import IntegrityError
from mfaf.tests._helpers import fresh_db, seed_case, cleanup


class TestCustody(unittest.TestCase):
    def setUp(self):
        self.db, self.d = fresh_db()
        seed_case(self.db)
        self.log = CustodyLog(self.db)

    def tearDown(self):
        cleanup(self.db, self.d)

    def test_append_and_chain_valid(self):
        self.log.append("ex1", "CASE_CREATED", case_id="CASE-T")
        self.log.append("ex1", "DEVICE_IDENTIFIED", case_id="CASE-T", metadata={"d": "dev1"})
        v = self.log.verify_chain()
        self.assertTrue(v["valid"]); self.assertEqual(v["count"], 2)

    def test_unknown_action_rejected(self):
        with self.assertRaises(IntegrityError):
            self.log.append("ex1", "MAGIC_BYPASS")

    def test_actor_required(self):
        with self.assertRaises(IntegrityError):
            self.log.append("", "CASE_CREATED")

    def test_tamper_detected(self):
        self.log.append("ex1", "CASE_CREATED", case_id="CASE-T")
        self.log.append("ex1", "EVIDENCE_CREATED", case_id="CASE-T", evidence_id="EV-1")
        # تعديل تاريخي مباشر في القاعدة يجب أن يكسر السلسلة
        self.db.conn.execute("UPDATE chain_of_custody_events SET actor='mallory' WHERE seq=1")
        self.db.conn.commit()
        v = self.log.verify_chain()
        self.assertFalse(v["valid"]); self.assertEqual(v["broken_at"], 1)

    def test_append_only_survives_new_events(self):
        for _ in range(5):
            self.log.append("ex1", "EVIDENCE_ANALYZED", case_id="CASE-T")
        self.assertTrue(self.log.verify_chain()["valid"])
        self.assertEqual(len(self.log.list_events(case_id="CASE-T")), 5)


if __name__ == "__main__":
    unittest.main()
