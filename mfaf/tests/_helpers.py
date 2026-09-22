import os, tempfile, shutil
from mfaf.db import MFAFDatabase
from mfaf import models as M


def fresh_db():
    d = tempfile.mkdtemp(prefix="mfaf_test_")
    db = MFAFDatabase(os.path.join(d, "mfaf.db"))
    return db, d


def seed_case(db, case="CASE-T", examiner="ex1", device="dev1"):
    db.add_examiner(M.Examiner(examiner, "Tester", "Lab"))
    db.add_case(M.Case(case, "Title", examiner, legal_authority="REF-1"))
    db.add_device(M.Device(device, case_id=case, os_family="android",
                           connection_mode="mock", serial=None))
    return case, examiner, device


def cleanup(db, d):
    db.close()
    shutil.rmtree(d, ignore_errors=True)
