import os, tempfile, unittest
from mfaf import validation as V
from mfaf.errors import ValidationError


class TestValidation(unittest.TestCase):
    def test_malicious_filenames(self):
        for bad in ["../etc/passwd", "a/b.txt", "..", ".", "", "x/../y", "\x00evil", "sub\\win.txt"]:
            with self.assertRaises(ValidationError):
                V.safe_filename(bad)
        self.assertEqual(V.safe_filename("evidence_01.bin"), "evidence_01.bin")

    def test_path_traversal_blocked(self):
        base = tempfile.mkdtemp()
        with self.assertRaises(ValidationError):
            V.resolve_within(base, "../../etc/passwd")
        with self.assertRaises(ValidationError):
            V.resolve_within(base, "/etc/passwd")
        ok = V.resolve_within(base, "sub/child.txt")
        self.assertTrue(ok.startswith(os.path.realpath(base)))

    def test_oversized_rejected(self):
        with self.assertRaises(ValidationError):
            V.validate_size(10, max_bytes=5)
        with self.assertRaises(ValidationError):
            V.validate_size(-1)
        self.assertEqual(V.validate_size(5, max_bytes=5), 5)

    def test_identifier_and_control_chars(self):
        with self.assertRaises(ValidationError):
            V.validate_identifier("bad id with space")
        with self.assertRaises(ValidationError):
            V.validate_identifier("../evil")
        with self.assertRaises(ValidationError):
            V.clean_text("line\nbreak", "f")  # control char in single-line field
        self.assertEqual(V.validate_identifier("CASE-2026_001"), "CASE-2026_001")


if __name__ == "__main__":
    unittest.main()
