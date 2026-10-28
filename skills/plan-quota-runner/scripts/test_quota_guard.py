import unittest
from quota_guard import decide

class GuardTests(unittest.TestCase):
    def run_case(self, **changes):
        d=dict(now='2026-10-28T18:59:00+08:00',
          protected_intervals=[dict(start='2026-10-28T19:00:00+08:00',end='2026-10-29T00:00:00+08:00')],
          authorization_end='2026-11-01T19:48:32+08:00',ordinary_usage_allowed=True,
          short_used_percent=40,weekly_used_percent=99,
          short_resets_at='2026-10-28T22:00:00+08:00')
        d.update(changes)
        return decide(d)
    def test_work_until_actual_start_without_week_reserve(self):
        r=self.run_case();self.assertEqual(r['decision'],'WORK');self.assertEqual(r['weekly_reserve_percent'],0)
        self.assertEqual(r['stop_before'],'2026-10-28T19:00:00+08:00')
    def test_start_inclusive_end_exclusive(self):
        self.assertEqual(self.run_case(now='2026-10-28T19:00:00+08:00')['decision'],'RESERVED')
        self.assertEqual(self.run_case(now='2026-10-29T00:00:00+08:00')['decision'],'WORK')
    def test_legacy_no_reserve_flag_cannot_remove_use_period(self):
        self.assertEqual(self.run_case(now='2026-10-28T20:00:00+08:00',personal_reservation_enabled=False)['decision'],'RESERVED')
    def test_night_work(self):
        self.assertEqual(self.run_case(now='2026-10-29T02:00:00+08:00')['decision'],'WORK')
    def test_reset_in_use_moves_to_end(self):
        r=self.run_case(short_used_percent=100)
        self.assertEqual(r['next_eligible_check'],'2026-10-29T00:00:00+08:00')
    def test_reset_plus_two_minutes(self):
        r=self.run_case(short_used_percent=100,short_resets_at='2026-10-28T18:59:30+08:00',protected_intervals=[])
        self.assertEqual(r['next_eligible_check'],'2026-10-28T19:01:30+08:00')
    def test_next_week_reset_allowed_before_deadline(self):
        r=self.run_case(weekly_used_percent=100,weekly_resets_at='2026-10-30T08:00:00+08:00')
        self.assertEqual(r['decision'],'WAIT_QUOTA')
    def test_fresh_week_is_work(self):
        self.assertEqual(self.run_case(weekly_used_percent=1)['decision'],'WORK')
    def test_authorized_card_near_exhaustion(self):
        self.assertEqual(self.run_case(reset_credit_authorized=True,reset_credits_available=1)['decision'],'RESET_CREDIT')
    def test_card_not_consumed_in_user_time(self):
        self.assertEqual(self.run_case(now='2026-10-28T20:00:00+08:00',reset_credit_authorized=True,reset_credits_available=1)['decision'],'RESERVED')
    def test_no_implicit_card_authorization(self):
        self.assertEqual(self.run_case(reset_credits_available=2)['decision'],'WORK')
    def test_no_blind_second_card(self):
        for field in ['reset_credit_attempt_pending','reset_credit_attempt_failed']:
            self.assertEqual(self.run_case(reset_credit_authorized=True,reset_credits_available=2,**{field:True})['decision'],'WORK')
    def test_missing_readings(self):
        self.assertEqual(self.run_case(weekly_used_percent=None)['decision'],'UNKNOWN')
    def test_deadline_not_extended(self):
        self.assertEqual(self.run_case(now='2026-11-01T19:48:32+08:00')['decision'],'RESERVED')
    def test_no_deadline_is_not_week_reset(self):
        self.assertEqual(self.run_case(authorization_end=None)['decision'],'WORK')
    def test_invalid_input(self):
        for v in [101,-1,True,float('nan')]:
            with self.assertRaises(ValueError):self.run_case(weekly_used_percent=v)
        with self.assertRaises(ValueError):self.run_case(now='2026-10-28T18:00:00')

if __name__=='__main__':unittest.main()
