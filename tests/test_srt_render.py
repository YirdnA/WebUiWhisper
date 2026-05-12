from __future__ import annotations

from app.srt import _srt_ts, render_srt


def test_timestamp_format():
    assert _srt_ts(0) == "00:00:00,000"
    assert _srt_ts(1.234) == "00:00:01,234"
    assert _srt_ts(3661.5) == "01:01:01,500"
    assert _srt_ts(-1) == "00:00:00,000"


def test_render_srt_known_segments():
    segs = [
        {"start_sec": 0.0, "end_sec": 2.5, "speaker": "SPEAKER_00", "text": "hello"},
        {"start_sec": 2.5, "end_sec": 4.0, "speaker": "?", "text": "world"},
        {"start_sec": 4.0, "end_sec": 5.0, "speaker": "", "text": "no speaker"},
    ]
    out = render_srt(segs)
    lines = out.splitlines()
    # SRT requires monotonic index starting at 1
    assert lines[0] == "1"
    assert lines[1] == "00:00:00,000 --> 00:00:02,500"
    assert lines[2] == "SPEAKER_00: hello"
    # Unknown speaker drops the prefix
    assert "?: " not in out
    assert ": no speaker" not in out
    # Trailing blank line between entries
    assert out.endswith("\n\n") or out.endswith("\n")


def test_render_handles_inverted_end_time():
    out = render_srt([{"start_sec": 5.0, "end_sec": 1.0, "speaker": "A", "text": "x"}])
    assert "00:00:05,000 --> 00:00:05,000" in out
