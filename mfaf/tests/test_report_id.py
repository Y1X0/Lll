"""
Regression: a single authoritative Report ID must appear identically in
  (1) CLI output  (2) report document  (3) reports table  (4) REPORT_GENERATED custody event.
"""
import io, json, os, re, tempfile, shutil, unittest
from contextlib import redirect_stdout
from mfaf.cli import main


class TestReportIdConsistency(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mfaf_rptid_")
        self.db = os.path.join(self.d, "m.db")
        self._run("examiner", "add", "--id", "ex1", "--name", "A")
        self._run("case", "create", "--id", "C1", "--title", "T", "--examiner", "ex1")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _run(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--db", self.db, *args])
        out = buf.getvalue().strip()
        try:
            return rc, json.loads(out) if out.startswith(("{", "[")) else out
        except json.JSONDecodeError:
            return rc, out

    def _db_report_id(self):
        import sqlite3
        c = sqlite3.connect(self.db)
        r = c.execute("SELECT report_id FROM reports ORDER BY rowid DESC LIMIT 1").fetchone()
        c.close()
        return r[0]

    def _custody_report_id(self):
        import sqlite3, json as j
        c = sqlite3.connect(self.db)
        r = c.execute("SELECT metadata FROM chain_of_custody_events "
                      "WHERE action='REPORT_GENERATED' ORDER BY seq DESC LIMIT 1").fetchone()
        c.close()
        return j.loads(r[0])["report_id"]

    def test_markdown_all_four_ids_match(self):
        out_path = os.path.join(self.d, "r.md")
        rc, cli = self._run("report", "generate", "--case", "C1",
                            "--format", "markdown", "--out", out_path)
        self.assertEqual(rc, 0)
        cli_id = cli["report_id"]
        doc = open(out_path, encoding="utf-8").read()
        doc_id = re.search(r"\*\*Report ID:\*\*\s*(RPT-[0-9a-f]+)", doc).group(1)
        self.assertEqual(cli_id, doc_id, "CLI id != document id")
        self.assertEqual(cli_id, self._db_report_id(), "CLI id != reports table id")
        self.assertEqual(cli_id, self._custody_report_id(), "CLI id != custody event id")

    def test_json_body_id_matches_cli(self):
        out_path = os.path.join(self.d, "r.json")
        rc, cli = self._run("report", "generate", "--case", "C1",
                            "--format", "json", "--out", out_path)
        self.assertEqual(rc, 0)
        body = json.load(open(out_path, encoding="utf-8"))
        self.assertEqual(cli["report_id"], body["report_id"])
        self.assertEqual(cli["report_id"], self._db_report_id())
        self.assertEqual(cli["report_id"], self._custody_report_id())


if __name__ == "__main__":
    unittest.main()
