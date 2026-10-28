#!/usr/bin/env python3
"""Read-only guard: actual use intervals, real quota, optional authorized reset card."""
import argparse
import json
import math
from datetime import datetime, timedelta


def stamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Every timestamp needs an explicit UTC offset')
    return dt


def percentage(value, name):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError(name + ' must be 0..100 or null')
    return value


def decide(data):
    now = stamp(data['now'])
    deadline = stamp(data['authorization_end']) if data.get('authorization_end') else None
    raw = data.get('protected_intervals')
    if raw is None:
        raw = ([{'start': data['protected_start'], 'end': data['protected_end']}]
               if data.get('protected_start') else [])
    if not isinstance(raw, list):
        raise ValueError('protected_intervals must be a list')
    merged = []
    for start, end in sorted((stamp(i['start']), stamp(i['end'])) for i in raw):
        if end <= start:
            raise ValueError('protected_end must be later than protected_start; midnight crosses dates')
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    short = percentage(data.get('short_used_percent'), 'short_used_percent')
    week = percentage(data.get('weekly_used_percent'), 'weekly_used_percent')
    allowed = data.get('ordinary_usage_allowed')
    if allowed is not None and not isinstance(allowed, bool):
        raise ValueError('ordinary_usage_allowed must be a boolean or null')
    authorized = data.get('reset_credit_authorized', False)
    if not isinstance(authorized, bool):
        raise ValueError('reset_credit_authorized must be a boolean')
    cards = data.get('reset_credits_available', 0)
    if isinstance(cards, bool) or not isinstance(cards, int) or cards < 0:
        raise ValueError('reset_credits_available must be a nonnegative integer')
    stops = [s for s, e in merged if s > now] + ([deadline] if deadline else [])
    output = dict(decision=None, weekly_reserve_percent=0,
                  authorization_end=deadline.isoformat() if deadline else None,
                  stop_before=min(stops).isoformat() if stops else None,
                  next_eligible_check=None, reason='')

    def finish(kind, reason, wake=None):
        if wake and deadline and wake >= deadline:
            wake = None
        output.update(decision=kind, reason=reason,
                      next_eligible_check=wake.isoformat() if wake else None)
        return output

    def outside_use(wake):
        for start, end in merged:
            if start <= wake < end:
                wake = end
        return wake

    if deadline and now >= deadline:
        return finish('RESERVED', 'Explicit task authorization ended')
    if any(start <= now < end for start, end in merged):
        return finish('RESERVED', 'User is using the computer; no task or model wakeups', outside_use(now))
    if allowed is None or short is None or week is None:
        return finish('UNKNOWN', 'Refresh real quota; missing readings are not zero')
    exhausted = [key for value, key in [(short, 'short_resets_at'), (week, 'weekly_resets_at')] if value >= 100]
    near = short >= 95 or week >= 95 or (not allowed and bool(exhausted))
    if near and authorized and cards and not data.get('reset_credit_attempt_pending') and not data.get('reset_credit_attempt_failed'):
        return finish('RESET_CREDIT', 'Checkpoint, verify an unexpired card, use one through an official entry, then re-read quota')
    if exhausted:
        if any(not data.get(k) for k in exhausted):
            return finish('UNKNOWN', 'Exhausted quota has no verified reset timestamp')
        wake = max(stamp(data[k]) for k in exhausted) + timedelta(minutes=2)
        if wake <= now:
            return finish('UNKNOWN', 'Stale reset: refresh actual quota before scheduling')
        wake = outside_use(wake)
        if deadline and wake >= deadline:
            return finish('RESERVED', 'Reset is outside explicit task authorization')
        return finish('WAIT_QUOTA', 'Wait for actual reset plus two minutes, outside user use', wake)
    if not allowed:
        return finish('UNKNOWN', 'Usage denied without an identified exhausted quota')
    return finish('WORK', 'Run a bounded increment until actual use starts; no weekly reserve')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    with open(parser.parse_args().input, encoding='utf-8') as stream:
        print(json.dumps(decide(json.load(stream)), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
