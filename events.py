"""Starboard's event calendar: major Star Citizen events for this month and the next three.

The list is data/events.json. "confirmed" events have dates announced by RSI; "expected"
events are yearly ones whose dates are not out yet, placed at their usual time.
"""

import datetime as dt
import json
import os

KINDS = {"expo": "SHOW", "holiday": "FESTIVAL", "community": "COMMUNITY", "freefly": "FREE FLY",
         "patch": "PATCH", "event": "EVENT"}


def _d(s):
    return dt.date.fromisoformat(s)


def load(data_dir):
    try:
        with open(os.path.join(data_dir, "events.json"), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for e in raw.get("events") or []:
        try:
            out.append(dict(e, start=_d(e["start"]), end=_d(e.get("end") or e["start"])))
        except (KeyError, ValueError):
            continue
    return sorted(out, key=lambda e: (e["start"], -(e["end"] - e["start"]).days))


def add_months(d, n):
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def window(today=None):
    """(first day of this month, last day of the month three months from now)."""
    today = today or dt.date.today()
    first = today.replace(day=1)
    return first, add_months(first, 4) - dt.timedelta(days=1)


def in_window(evts, today=None):
    lo, hi = window(today)
    return [e for e in evts if e["end"] >= lo and e["start"] <= hi]


def in_month(evts, month_first):
    last = add_months(month_first, 1) - dt.timedelta(days=1)
    return [e for e in evts if e["end"] >= month_first and e["start"] <= last]


def when(e):
    s, t = e["start"], e["end"]
    if s == t:
        return s.strftime("%b %d").upper()
    if s.month == t.month and s.year == t.year:
        return f"{s.strftime('%b %d').upper()} TO {t.strftime('%d')}"
    return f"{s.strftime('%b %d').upper()} TO {t.strftime('%b %d').upper()}"
