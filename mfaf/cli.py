"""
واجهة سطر أوامر MFAF. تفشل بأمان عند طلب عملية غير مدعومة/غير مصرّح بها.

الأوامر:
  mfaf case create|show|list
  mfaf device detect|list
  mfaf acquisition start
  mfaf evidence list|verify
  mfaf experiment create|run
  mfaf timeline show
  mfaf report generate
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

from .db import MFAFDatabase
from . import models as M
from .custody import CustodyLog
from .timeline import Timeline
from .acquisition import (AcquisitionEngine, MockAcquisitionProvider,
                          FilesystemAcquisitionProvider, UnavailableAcquisitionProvider,
                          verify_evidence_integrity)
from .mock_device import MockMobileDevice, MockDeviceConfig
from .auth_harness import AuthenticationHarness
from .report import ReportGenerator
from .experiments import get_definition, list_codes
from .v1_import import import_v1, V1ImportError
from .errors import MFAFError

PROVIDERS = {
    "mock": lambda: MockAcquisitionProvider(),
    "filesystem": lambda: FilesystemAcquisitionProvider(),
    "android": lambda: UnavailableAcquisitionProvider(
        "authorized Android acquisition requires supported tooling — NOT VERIFIED, physical device required"),
    "ios": lambda: UnavailableAcquisitionProvider(
        "authorized iOS import requires supported workflow — NOT VERIFIED, physical device required"),
}


def _out(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def build_parser():
    p = argparse.ArgumentParser(prog="mfaf", description="MFAF forensic research CLI")
    p.add_argument("--db", default="mfaf.db", help="مسار قاعدة البيانات")
    p.add_argument("--actor", default="cli", help="الفاعل لأحداث العهدة")
    sub = p.add_subparsers(dest="group", required=True)

    xm = sub.add_parser("examiner").add_subparsers(dest="cmd", required=True)
    xma = xm.add_parser("add"); xma.add_argument("--id", required=True)
    xma.add_argument("--name", required=True); xma.add_argument("--org", default=None)

    g = sub.add_parser("case").add_subparsers(dest="cmd", required=True)
    cc = g.add_parser("create"); cc.add_argument("--id", required=True); cc.add_argument("--title", required=True)
    cc.add_argument("--examiner", required=True); cc.add_argument("--authority", default=None)
    cs = g.add_parser("show"); cs.add_argument("--id", required=True)
    g.add_parser("list")

    d = sub.add_parser("device").add_subparsers(dest="cmd", required=True)
    dd = d.add_parser("detect"); dd.add_argument("--id", required=True); dd.add_argument("--case", default=None)
    dd.add_argument("--os", default="unknown"); dd.add_argument("--vid", default=None)
    dd.add_argument("--pid", default=None); dd.add_argument("--manufacturer", default=None)
    dd.add_argument("--model", default=None); dd.add_argument("--connection", default="usb")
    d.add_parser("list")

    a = sub.add_parser("acquisition").add_subparsers(dest="cmd", required=True)
    ast = a.add_parser("start"); ast.add_argument("--case", required=True)
    ast.add_argument("--device", required=True); ast.add_argument("--provider", required=True, choices=list(PROVIDERS))
    ast.add_argument("--source", default=None); ast.add_argument("--store", required=True)
    ast.add_argument("--examiner", default=None)

    e = sub.add_parser("evidence").add_subparsers(dest="cmd", required=True)
    el = e.add_parser("list"); el.add_argument("--case", default=None)
    ev = e.add_parser("verify"); ev.add_argument("--id", required=True)

    x = sub.add_parser("experiment").add_subparsers(dest="cmd", required=True)
    xc = x.add_parser("create"); xc.add_argument("--id", required=True); xc.add_argument("--case", required=True)
    xc.add_argument("--code", required=True, choices=list_codes()); xc.add_argument("--target", default="mock-target-1")
    xr = x.add_parser("run"); xr.add_argument("--id", required=True)
    xr.add_argument("--attempts", type=int, default=6)
    xr.add_argument("--correct-at", type=int, default=-1,
                    help="رقم المحاولة التي يكون فيها المدخل الاصطناعي الصحيح (-1=لا)")
    x.add_parser("defs")

    t = sub.add_parser("timeline").add_subparsers(dest="cmd", required=True)
    ts = t.add_parser("show"); ts.add_argument("--case", required=True)

    r = sub.add_parser("report").add_subparsers(dest="cmd", required=True)
    rg = r.add_parser("generate"); rg.add_argument("--case", required=True)
    rg.add_argument("--format", choices=["json", "markdown"], default="json")
    rg.add_argument("--out", default=None)
    v1 = sub.add_parser("v1").add_subparsers(dest="cmd", required=True)
    v1i = v1.add_parser("import"); v1i.add_argument("--file", required=True)
    v1i.add_argument("--case", required=True)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    db = MFAFDatabase(args.db)
    cust = CustodyLog(db)
    tl = Timeline(db)
    try:
        return _dispatch(args, db, cust, tl)
    except MFAFError as e:
        _out({"error": type(e).__name__, "message": str(e)})
        return 2
    finally:
        db.close()


def _dispatch(args, db, cust, tl):
    if args.group == "examiner" and args.cmd == "add":
        db.add_examiner(M.Examiner(args.id, args.name, args.org))
        _out({"created": args.id}); return 0

    if args.group == "case":
        if args.cmd == "create":
            db.add_case(M.Case(args.id, args.title, args.examiner, legal_authority=args.authority))
            cust.append(args.actor, "CASE_CREATED", case_id=args.id)
            _out({"created": args.id}); return 0
        if args.cmd == "show":
            _out(db.get_case(args.id)); return 0
        if args.cmd == "list":
            _out(db.list_cases()); return 0

    if args.group == "device":
        if args.cmd == "detect":
            dev = M.Device(args.id, case_id=args.case, os_family=args.os, usb_vid=args.vid,
                           usb_pid=args.pid, manufacturer=args.manufacturer, model=args.model,
                           connection_mode=args.connection, serial=None)
            db.add_device(dev)
            cust.append(args.actor, "DEVICE_IDENTIFIED", case_id=args.case,
                        metadata={"device_id": args.id})
            if args.case:
                tl.add(args.case, "DEVICE_IDENTIFIED", device_id=args.id)
            _out(M.to_dict(dev)); return 0
        if args.cmd == "list":
            _out(db.list_devices()); return 0

    if args.group == "acquisition" and args.cmd == "start":
        provider = PROVIDERS[args.provider]()
        eng = AcquisitionEngine(db, cust, tl)
        res = eng.run(args.case, args.device, provider, args.source, args.store,
                      examiner_id=args.examiner, actor=args.actor)
        _out({"acquisition_id": res["acquisition_id"], "status": res["status"],
              "reason": res.get("reason"), "evidence_count": len(res["evidence"])})
        return 0

    if args.group == "evidence":
        if args.cmd == "list":
            _out(db.list_evidence(args.case)); return 0
        if args.cmd == "verify":
            status = verify_evidence_integrity(db, args.id)
            cust.append(args.actor, "EVIDENCE_VERIFIED", evidence_id=args.id,
                        metadata={"status": status})
            _out({"evidence_id": args.id, "integrity_status": status}); return 0

    if args.group == "experiment":
        if args.cmd == "defs":
            _out({c: get_definition(c)["objective"] for c in list_codes()}); return 0
        if args.cmd == "create":
            defn = get_definition(args.code)
            db.add_experiment(M.Experiment(args.id, args.case, args.target, args.code,
                                           defn["objective"]))
            _out({"created": args.id, "code": args.code}); return 0
        if args.cmd == "run":
            row = db.conn.execute("SELECT * FROM experiments WHERE experiment_id=?",
                                  (args.id,)).fetchone()
            if not row:
                _out({"error": "NotFoundError", "message": f"experiment {args.id}"}); return 2
            dev = MockMobileDevice(); dev.connect()
            inputs = []
            for i in range(1, args.attempts + 1):
                inputs.append(dev.config.correct_input_id if i == args.correct_at
                              else f"SYNTH-WRONG-{i}")
            res = AuthenticationHarness(db, cust).run_experiment(args.id, dev, inputs, args.actor)
            _out({"experiment_id": args.id, "metrics": res["metrics"]}); return 0

    if args.group == "timeline" and args.cmd == "show":
        _out(tl.chronological(args.case)); return 0

    if args.group == "report" and args.cmd == "generate":
        rg = ReportGenerator(db)
        text = rg.render_markdown(args.case) if args.format == "markdown" else rg.render_json(args.case)
        rid = f"RPT-{uuid.uuid4().hex[:12]}"
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(args.out, 0o600)
            db.add_report(rid, args.case, args.format, args.out)
            cust.append(args.actor, "REPORT_GENERATED", case_id=args.case,
                        metadata={"report_id": rid, "path": args.out})
            _out({"report_id": rid, "path": args.out})
        else:
            db.add_report(rid, args.case, args.format, None)
            print(text)
        return 0
    if args.group == "v1" and args.cmd == "import":
        try:
            rec = import_v1(db, args.file, args.case, actor=args.actor, timeline=tl)
        except V1ImportError as e:
            _out({"error": "V1ImportError", "message": str(e)}); return 2
        # سجّل حدث عهدة للاستيراد (لا يقيّد V1 كناجح)
        cust.append(args.actor, "EVIDENCE_ANALYZED", case_id=args.case,
                    metadata={"v1_import": rec["import_id"],
                              "effective_status": rec["effective_status"]})
        _out({"import_id": rec["import_id"], "case_id": rec["case_id"],
              "declared_status": rec["declared_status"],
              "effective_status": rec["effective_status"],
              "observation_count": rec["observation_count"],
              "timeline_events_created": rec["timeline_events_created"],
              "note": "schema valid; V1 NOT auto-verified — status derived from examiner observations"})
        return 0

    _out({"error": "usage"}); return 1


if __name__ == "__main__":
    sys.exit(main())
