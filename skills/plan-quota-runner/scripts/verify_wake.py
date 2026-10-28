#!/usr/bin/env python3
"""Read-only check of one task's actual desktop schedule, never its prompt/account data."""
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset")
    return parsed


def verify(row, expected_nominal, reset_at, now):
    expected, reset, current = map(timestamp, (expected_nominal, reset_at, now))
    actual = row.get("next_run_at")
    nominal = row.get("next_run_nominal_at")
    result = {"verified": False, "status": row.get("status"), "last_run_at": row.get("last_run_at")}
    if row.get("status") != "ACTIVE" or actual is None or nominal is None:
        return {**result, "reason": "Active status and both actual/nominal next-run timestamps are required."}
    actual_time = dt.datetime.fromtimestamp(actual / 1000, dt.timezone.utc)
    nominal_time = dt.datetime.fromtimestamp(nominal / 1000, dt.timezone.utc)
    result.update(next_run_at=actual_time.astimezone(expected.tzinfo).isoformat(),
                  next_run_nominal_at=nominal_time.astimezone(expected.tzinfo).isoformat(),
                  jitter_seconds=(actual_time - nominal_time).total_seconds())
    if nominal_time != expected:
        return {**result, "reason": "Actual scheduling database nominal time differs from the disclosed fixed time; check UTC/timezone interpretation."}
    if actual_time < reset + dt.timedelta(minutes=2):
        return {**result, "reason": "Actual dispatch is earlier than the verified quota reset plus two minutes; move the fixed node later."}
    if actual_time <= current:
        return {**result, "reason": "Actual next-run time is already past; check last_run and run records before assuming a wake occurred."}
    return {**result, "verified": True, "reason": "The next scheduled time is correct and satisfies reset+2min; future execution/offline delivery is not guaranteed."}


def read_schedule(database, automation_id, thread_id):
    uri = Path(database).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT status,next_run_at,next_run_nominal_at,last_run_at,target_thread_id FROM automations WHERE id=?", (automation_id,)).fetchone()
        if row is None or row["target_thread_id"] != thread_id:
            raise ValueError("No schedule belonging to the expected task thread was found.")
        return dict(row)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("database", "automation-id", "thread-id", "expected-nominal", "reset-at", "now"):
        p.add_argument("--" + key, required=True)
    a = p.parse_args()
    try:
        result = verify(read_schedule(a.database, a.automation_id, a.thread_id), a.expected_nominal, a.reset_at, a.now)
    except (ValueError, OSError, sqlite3.Error) as error:
        # Do not expose query text, paths or full configuration in diagnostics.
        result = {"verified": False, "reason": "Read-only schedule verification unavailable; inspect schema/access and supplied timezone-aware timestamps.", "error_type": type(error).__name__}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
