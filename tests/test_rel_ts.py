"""Relative-time Jinja filter used by the Queue page."""
from __future__ import annotations

import datetime as _dt

from app.main import _rel_ts


def _ago(seconds: float) -> float:
    return _dt.datetime.now(tz=_dt.timezone.utc).timestamp() - seconds


def test_seconds_ago():
    assert _rel_ts(_ago(0)) == "0 s ago"
    assert _rel_ts(_ago(30)) == "30 s ago"


def test_minutes_ago():
    assert _rel_ts(_ago(60)) == "1 min ago"
    assert _rel_ts(_ago(60 * 12)) == "12 min ago"


def test_hours_ago():
    assert _rel_ts(_ago(3600)) == "1 h ago"
    assert _rel_ts(_ago(3600 * 3)) == "3 h ago"


def test_yesterday_then_days_ago():
    assert _rel_ts(_ago(86400 + 100)) == "yesterday"
    assert _rel_ts(_ago(86400 * 3)) == "3 d ago"


def test_absolute_date_for_older():
    out = _rel_ts(_ago(86400 * 30))
    # Should be a YYYY-MM-DD string.
    parsed = _dt.datetime.strptime(out, "%Y-%m-%d")
    assert parsed.year >= 2025


def test_future_falls_back_to_date():
    future = _dt.datetime.now(tz=_dt.timezone.utc).timestamp() + 60
    out = _rel_ts(future)
    _dt.datetime.strptime(out, "%Y-%m-%d")  # parses cleanly


def test_bad_input_passes_through():
    assert _rel_ts(None) == "None"
    assert _rel_ts("not a number") == "not a number"
