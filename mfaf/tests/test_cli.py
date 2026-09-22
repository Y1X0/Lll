import io, json, os, unittest
from contextlib import redirect_stdout
from mfaf.cli import main
from mfaf.tests._helpers import fresh_db, cleanup
import tempfile, shutil


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mfaf_cli_")
        self.db = os.path.join(self.d, "m.db")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _run(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--db", self.db, *args])
        out = buf.getvalue().strip()
        try:
            parsed = json.loads(out) if out else None
        except json.JSONDecodeError:
            parsed = out
        return rc, parsed

    def test_full_workflow(self):
        self.assertEqual(self._run("examiner", "add", "--id", "ex1", "--name", "A")[0], 0)
        self.assertEqual(self._run("case", "create", "--id", "C1", "--title", "T",
                                   "--examiner", "ex1", "--authority", "REF")[0], 0)
        self.assertEqual(self._run("device", "detect", "--id", "d1", "--case", "C1",
                                   "--os", "android")[0], 0)
        rc, out = self._run("acquisition", "start", "--case", "C1", "--device", "d1",
                            "--provider", "mock", "--store", os.path.join(self.d, "st"))
        self.assertEqual(rc, 0); self.assertEqual(out["status"], "COMPLETED")

    def test_android_provider_fails_safely(self):
        self._run("examiner", "add", "--id", "ex1", "--name", "A")
        self._run("case", "create", "--id", "C1", "--title", "T", "--examiner", "ex1")
        self._run("device", "detect", "--id", "d1", "--case", "C1", "--os", "android")
        rc, out = self._run("acquisition", "start", "--case", "C1", "--device", "d1",
                            "--provider", "android", "--store", os.path.join(self.d, "st2"))
        self.assertEqual(rc, 0)
        self.assertEqual(out["status"], "NOT_AVAILABLE")   # فشل آمن، لا انهيار

    def test_experiment_run_and_report(self):
        self._run("examiner", "add", "--id", "ex1", "--name", "A")
        self._run("case", "create", "--id", "C1", "--title", "T", "--examiner", "ex1")
        self._run("experiment", "create", "--id", "X1", "--case", "C1", "--code", "EXP-005")
        rc, out = self._run("experiment", "run", "--id", "X1", "--attempts", "6")
        self.assertEqual(rc, 0)
        self.assertTrue(out["metrics"]["rate_limit_detected"])
        rc, rep = self._run("report", "generate", "--case", "C1", "--format", "json")
        self.assertEqual(rc, 0)

    def test_missing_case_safe_error(self):
        rc, out = self._run("case", "show", "--id", "NOPE")
        self.assertEqual(rc, 2)                # يفشل بأمان لا يرمي
        self.assertEqual(out["error"], "NotFoundError")


if __name__ == "__main__":
    unittest.main()
