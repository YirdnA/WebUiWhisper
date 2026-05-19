"""Audio route Range-header parsing + chunked file iteration.

The HTTP-level wiring is thin; the logic that matters is `_parse_range` (RFC 7233
single-range subset) and `_file_iter` (streaming reader). Both are pure functions
on filesystem + bytes, so we unit-test them directly without spinning a FastAPI app."""
from __future__ import annotations

import pytest

from app.routes.audio import _file_iter, _parse_range


def test_parse_range_full_request():
    start, end = _parse_range("bytes=0-99", size=1000)
    assert (start, end) == (0, 99)


def test_parse_range_open_end_clamps_to_size():
    start, end = _parse_range("bytes=500-", size=1000)
    assert (start, end) == (500, 999)


def test_parse_range_suffix_form_returns_last_n_bytes():
    start, end = _parse_range("bytes=-100", size=1000)
    assert (start, end) == (900, 999)


def test_parse_range_end_past_eof_clamps(tmp_path):
    # Per RFC 7233 the end is clamped to size-1, not an error.
    start, end = _parse_range("bytes=999-1500", size=1000)
    assert (start, end) == (999, 999)


@pytest.mark.parametrize("header", ["bytes=1500-2000", "bytes=10-5"])
def test_parse_range_unsatisfiable_raises(header):
    with pytest.raises(ValueError):
        _parse_range(header, size=1000)


def test_parse_range_rejects_malformed():
    with pytest.raises(ValueError):
        _parse_range("not-a-range", size=1000)


def test_file_iter_returns_exact_byte_slice(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(bytes(range(256)) * 4)  # 1024 bytes, predictable content
    chunks = list(_file_iter(p, start=100, end=199))
    out = b"".join(chunks)
    assert len(out) == 100
    assert out == bytes(range(256))[100:200]
