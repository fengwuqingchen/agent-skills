import datetime as dt
import tempfile
import sqlite3
import unittest
from pathlib import Path
from verify_wake import verify, read_schedule


def ms(value):
    return int(dt.datetime.fromisoformat(value).timestamp() * 1000)


class WakeTests(unittest.TestCase):
    nominal = "2026-10-28T05:48:00+08:00"
    reset = "2026-10-28T05:41:47+08:00"
    now = "2026-10-28T01:00:00+08:00"

    def row(self, actual="2026-10-28T05:50:53+08:00", nominal=None):
        return {"status": "ACTIVE", "next_run_at": ms(actual), "next_run_nominal_at": ms(nominal or self.nominal), "last_run_at": None}

    def test_correct_real_time(self):
        r = verify(self.row(), self.nominal, self.reset, self.now)
        self.assertTrue(r["verified"])
        self.assertEqual(r["jitter_seconds"], 173)

    def test_observed_eight_hour_drift(self):
        r = verify(self.row(nominal="2026-10-28T08:30:00+08:00"), "2026-10-28T00:30:00+08:00", self.reset, self.now)
        self.assertFalse(r["verified"])
        self.assertIn("timezone", r["reason"])

    def test_early_jitter_cannot_cross_two_minute_buffer(self):
        r = verify(self.row(actual="2026-10-28T05:43:46+08:00"), self.nominal, self.reset, self.now)
        self.assertFalse(r["verified"])
        self.assertTrue(verify(self.row(actual="2026-10-28T05:43:47+08:00"), self.nominal, self.reset, self.now)["verified"])

    def test_cross_midnight_utc_equivalence(self):
        self.assertTrue(verify(self.row(), "2026-10-27T21:48:00Z", self.reset, self.now)["verified"])

    def test_missing_paused_or_overdue_is_not_verified(self):
        for change in ({"status": "PAUSED"}, {"next_run_at": None}, {"next_run_nominal_at": None}):
            self.assertFalse(verify({**self.row(), **change}, self.nominal, self.reset, self.now)["verified"])
        self.assertFalse(verify(self.row(), self.nominal, self.reset, "2026-10-28T06:00:00+08:00")["verified"])

    def test_read_scope_and_readonly_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "schedule.db"
            with sqlite3.connect(path) as c:
                c.execute("CREATE TABLE automations(id,status,next_run_at,next_run_nominal_at,last_run_at,target_thread_id)")
                c.execute("INSERT INTO automations VALUES(?,?,?,?,?,?)", ("task", "ACTIVE", 1, 2, None, "thread"))
            before = path.read_bytes()
            self.assertEqual(read_schedule(path, "task", "thread")["next_run_at"], 1)
            with self.assertRaises(ValueError):
                read_schedule(path, "task", "unrelated-thread")
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
