"""Disk dashboard helpers: directory size + per-day transcript histogram."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path

from app.routes.disk import HISTOGRAM_DAYS, _bucket_by_day, _dir_size, _human


def test_dir_size_returns_zero_for_missing_path(tmp_path):
    assert _dir_size(tmp_path / "missing") == (0, 0)


def test_dir_size_returns_zero_for_empty_dir(tmp_path):
    assert _dir_size(tmp_path) == (0, 0)


def test_dir_size_sums_recursive_files(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    (tmp_path / "b.bin").write_bytes(b"y" * 250)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.bin").write_bytes(b"z" * 50)
    (sub / "deeper").mkdir()
    (sub / "deeper" / "d.bin").write_bytes(b"q" * 7)
    assert _dir_size(tmp_path) == (407, 4)


def test_dir_size_skips_symlinks(tmp_path):
    (tmp_path / "real.bin").write_bytes(b"hi")
    (tmp_path / "link.bin").symlink_to(tmp_path / "real.bin")
    size, count = _dir_size(tmp_path)
    assert size == 2
    assert count == 1


def test_human_renders_units():
    assert _human(0) == "0 B"
    assert _human(512) == "512 B"
    assert _human(1024) == "1.0 KiB"
    assert _human(1024 * 1024) == "1.0 MiB"
    assert _human(int(2.5 * 1024 ** 3)) == "2.5 GiB"


@dataclass
class _Summary:
    mtime: float


def _epoch(d: _dt.date) -> float:
    return _dt.datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=_dt.timezone.utc).timestamp()


def test_bucket_by_day_returns_full_window_oldest_first():
    today = _dt.datetime.now(tz=_dt.timezone.utc).date()
    summaries = [
        _Summary(mtime=_epoch(today)),
        _Summary(mtime=_epoch(today)),
        _Summary(mtime=_epoch(today - _dt.timedelta(days=2))),
    ]
    out = _bucket_by_day(summaries, days=HISTOGRAM_DAYS)
    assert len(out) == HISTOGRAM_DAYS
    assert out[-1] == (today, 2)
    assert out[-3] == (today - _dt.timedelta(days=2), 1)
    # Pad days have zero counts.
    zero_days = sum(1 for _, c in out if c == 0)
    assert zero_days == HISTOGRAM_DAYS - 2  # two distinct buckets used


def test_bucket_by_day_drops_old_and_future_entries():
    today = _dt.datetime.now(tz=_dt.timezone.utc).date()
    summaries = [
        _Summary(mtime=_epoch(today - _dt.timedelta(days=100))),  # too old
        _Summary(mtime=_epoch(today + _dt.timedelta(days=2))),    # future (clock skew)
        _Summary(mtime=_epoch(today)),
    ]
    out = _bucket_by_day(summaries, days=7)
    total = sum(c for _, c in out)
    assert total == 1
    assert out[-1] == (today, 1)
