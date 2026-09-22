"""مقاييس قابلة للقراءة آليًا — دون استنتاج خلاصات أمنية غير مدعومة."""
from __future__ import annotations


def summarize_auth_events(events: list[dict]) -> dict:
    if not events:
        return {
            "authentication_attempt_count": 0, "authentication_failure_count": 0,
            "authentication_success_count": 0, "average_response_time_ms": 0.0,
            "minimum_response_time_ms": 0.0, "maximum_response_time_ms": 0.0,
            "rate_limit_detected": False, "lockout_detected": False,
        }
    times = [e["response_time_ms"] for e in events]
    fails = sum(1 for e in events if e["result"] == "FAIL")
    succ = sum(1 for e in events if e["result"] == "SUCCESS")
    return {
        "authentication_attempt_count": len(events),
        "authentication_failure_count": fails,
        "authentication_success_count": succ,
        "average_response_time_ms": round(sum(times) / len(times), 3),
        "minimum_response_time_ms": round(min(times), 3),
        "maximum_response_time_ms": round(max(times), 3),
        "rate_limit_detected": any(e["rate_limit_state"] for e in events),
        "lockout_detected": any(e["lockout_state"] for e in events),
    }


def evidence_metrics(evidence_rows: list[dict]) -> dict:
    total = sum(int(e.get("byte_size") or 0) for e in evidence_rows)
    verified = sum(1 for e in evidence_rows if e.get("integrity_status") == "VERIFIED")
    return {
        "evidence_count": len(evidence_rows),
        "evidence_total_bytes": total,
        "hash_verification_success": verified,
    }


def timeline_metrics(events: list[dict]) -> dict:
    return {"timeline_event_count": len(events)}
