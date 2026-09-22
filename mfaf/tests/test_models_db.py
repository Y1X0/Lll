import unittest
from mfaf import models as M
from mfaf.errors import IntegrityError, NotFoundError
from mfaf.tests._helpers import fresh_db, seed_case, cleanup


class TestModelsDB(unittest.TestCase):
    def setUp(self):
        self.db, self.d = fresh_db()

    def tearDown(self):
        cleanup(self.db, self.d)

    def test_case_creation_and_show(self):
        seed_case(self.db)
        c = self.db.get_case("CASE-T")
        self.assertEqual(c["status"], "OPEN")
        self.assertEqual(c["legal_authority"], "REF-1")

    def test_missing_case_raises(self):
        with self.assertRaises(NotFoundError):
            self.db.get_case("NOPE")

    def test_duplicate_case_rejected(self):
        seed_case(self.db)
        with self.assertRaises(IntegrityError):
            self.db.add_case(M.Case("CASE-T", "again", "ex1"))

    def test_device_serial_explicit_null(self):
        seed_case(self.db)
        self.assertIsNone(self.db.get_device("dev1")["serial"])

    def test_evidence_fk_and_duplicate(self):
        case, ex, dev = seed_case(self.db)
        e = M.Evidence("EV-1", case, dev, None, "file", "a.bin", "/tmp/a.bin", 10, sha256="x")
        self.db.add_evidence(e)
        with self.assertRaises(IntegrityError):      # duplicate id
            self.db.add_evidence(e)
        with self.assertRaises(IntegrityError):      # orphan case
            self.db.add_evidence(M.Evidence("EV-2", "NOPE", dev, None, "file", "b", "/b", 1))

    def test_invalid_choices_rejected(self):
        seed_case(self.db)
        from mfaf.errors import ValidationError
        with self.assertRaises(ValidationError):
            self.db.add_device(M.Device("d2", os_family="martian"))


if __name__ == "__main__":
    unittest.main()
