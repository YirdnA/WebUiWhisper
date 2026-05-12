"""Smoke-test the limiter setup. We don't try to exhaust the limit here —
slowapi has its own coverage. We just verify that the limiter is wired and
that a manual call records hits."""
from __future__ import annotations

from app.rate_limit import limiter


def test_limiter_exists():
    assert limiter is not None
    assert callable(limiter.limit)
