import os, unittest
from mfaf.acquisition import (AcquisitionEngine, MockAcquisitionProvider,
                              FilesystemAcquisitionProvider, UnavailableAcquisitionProvider,
                              verify_evidence_integrity)
from mfaf.custody import CustodyLog
from mfaf.timeline import Timeline
from mfaf.tests._helpers import fresh_db, seed_case, cleanup


class TestAcquisition(unittest.TestCase):
    def setUp(self):
        self.db, self.d = fresh_db()
        seed_case(self.db)
        self.eng = AcquisitionEngine(self.db, CustodyLog(self.db), Timeline(self.db))
        self.store = os.path.join(self.d, "store")

    def tearDown(self):
        cleanup(self.db, self.d)

    def test_mock_acquisition_completed_and_verified(self):
        r = self.eng.run("CASE-T", "dev1", MockAcquisitionProvider(), None, self.store, "ex1")
        self.assertEqual(r["status"], "COMPLETED")
        self.assertEqual(len(r["evidence"]), 1)
        ev_id = r["evidence"][0]["evidence_id"]
        self.assertEqual(verify_evidence_integrity(self.db, ev_id), "VERIFIED")

    def test_unavailable_is_valid_result(self):
        r = self.eng.run("CASE-T", "dev1",
                         UnavailableAcquisitionProvider("no authorized path"),
                         None, self.store, "ex1")
        self.assertEqual(r["status"], "NOT_AVAILABLE")
        self.assertIn("no authorized path", r["reason"])
        self.assertEqual(r["evidence"], [])

    def test_filesystem_acquisition(self):
        src = os.path.join(self.d, "src"); os.makedirs(src)
        with open(os.path.join(src, "data1.bin"), "wb") as f:
            f.write(b"dataset-1")
        r = self.eng.run("CASE-T", "dev1", FilesystemAcquisitionProvider(), src, self.store, "ex1")
        self.assertEqual(r["status"], "COMPLETED")
        self.assertEqual(len(r["evidence"]), 1)

    def test_filesystem_oversize_rejected(self):
        src = os.path.join(self.d, "src2"); os.makedirs(src)
        with open(os.path.join(src, "big.bin"), "wb") as f:
            f.write(b"x" * 100)
        prov = FilesystemAcquisitionProvider(max_bytes=10)
        from mfaf.errors import ValidationError
        with self.assertRaises(ValidationError):
            self.eng.run("CASE-T", "dev1", prov, src, self.store, "ex1")

    def test_corrupted_evidence_detected_as_mismatch(self):
        r = self.eng.run("CASE-T", "dev1", MockAcquisitionProvider(), None, self.store, "ex1")
        ev = self.db.get_evidence(r["evidence"][0]["evidence_id"])
        with open(ev["storage_path"], "ab") as f:   # افساد المحتوى بعد التجزئة
            f.write(b"TAMPER")
        self.assertEqual(verify_evidence_integrity(self.db, ev["evidence_id"]), "MISMATCH")

    def test_missing_evidence_detected(self):
        r = self.eng.run("CASE-T", "dev1", MockAcquisitionProvider(), None, self.store, "ex1")
        ev = self.db.get_evidence(r["evidence"][0]["evidence_id"])
        os.remove(ev["storage_path"])
        self.assertEqual(verify_evidence_integrity(self.db, ev["evidence_id"]), "MISSING")

    def test_manifest_written(self):
        r = self.eng.run("CASE-T", "dev1", MockAcquisitionProvider(), None, self.store, "ex1")
        self.assertTrue(os.path.isfile(r["manifest_path"]))

    def test_stored_files_have_strict_permissions(self):
        r = self.eng.run("CASE-T", "dev1", MockAcquisitionProvider(), None, self.store, "ex1")
        mode = os.stat(r["evidence"][0]["storage_path"]).st_mode & 0o777
        self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
