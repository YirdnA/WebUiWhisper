"""render_txt — plain and timecoded TXT exports."""
from __future__ import annotations

from app.txt import render_txt


# Minimal segment dicts matching what the whisper service writes.
def _seg(start, end, speaker, text, *, start_time=None, end_time=None):
    out = {"start_sec": start, "end_sec": end, "speaker": speaker, "text": text}
    if start_time is not None:
        out["start_time"] = start_time
    if end_time is not None:
        out["end_time"] = end_time
    return out


def test_empty_segments_returns_empty_string_both_modes():
    assert render_txt([], with_timecodes=True) == ""
    assert render_txt([], with_timecodes=False) == ""


def test_plain_text_collapses_when_only_question_mark_speaker():
    segs = [
        _seg(0.0, 2.0, "?", "Hello world."),
        _seg(2.0, 4.0, "?", "Second sentence."),
    ]
    out = render_txt(segs, with_timecodes=False)
    assert out == "Hello world.\nSecond sentence.\n"
    assert "?:" not in out


def test_plain_text_collapses_when_single_named_speaker():
    """One speaker, even named, gets no header line — clean prose."""
    segs = [
        _seg(0.0, 2.0, "A", "Hello."),
        _seg(2.0, 4.0, "A", "Again."),
    ]
    out = render_txt(segs, with_timecodes=False)
    assert out == "Hello.\nAgain.\n"


def test_plain_text_emits_header_on_speaker_change():
    segs = [
        _seg(0.0, 2.0, "A", "Alice says hi."),
        _seg(2.0, 4.0, "B", "Bob replies."),
        _seg(4.0, 6.0, "A", "Alice again."),
    ]
    out = render_txt(segs, with_timecodes=False)
    expected = (
        "A:\n"
        "Alice says hi.\n"
        "\n"
        "B:\n"
        "Bob replies.\n"
        "\n"
        "A:\n"
        "Alice again.\n"
    )
    assert out == expected


def test_plain_text_skips_empty_text_segments():
    segs = [
        _seg(0.0, 2.0, "A", "Hello."),
        _seg(2.0, 3.0, "A", "   "),  # whitespace-only
        _seg(3.0, 4.0, "B", "Hi."),
    ]
    out = render_txt(segs, with_timecodes=False)
    assert out == "A:\nHello.\n\nB:\nHi.\n"


def test_timecoded_uses_string_times_when_present():
    segs = [
        _seg(0.59, 23.32, "A", "First line.",
             start_time="00:00:00.590", end_time="00:00:23.320"),
        _seg(23.32, 25.0, "?", "Second.",
             start_time="00:00:23.320", end_time="00:00:25.000"),
    ]
    out = render_txt(segs, with_timecodes=True)
    assert out == (
        "[00:00:00.590 - 00:00:23.320] A: First line.\n"
        "[00:00:23.320 - 00:00:25.000] ?: Second.\n"
    )


def test_timecoded_falls_back_to_sec_when_string_missing():
    segs = [_seg(61.5, 122.25, "S0", "hi")]
    out = render_txt(segs, with_timecodes=True)
    # 61.5 s = 00:01:01.500, 122.25 s = 00:02:02.250
    assert out == "[00:01:01.500 - 00:02:02.250] S0: hi\n"


def test_missing_speaker_renders_as_question_mark():
    segs = [_seg(0.0, 1.0, None, "noop")]
    out = render_txt(segs, with_timecodes=True)
    assert out.startswith("[00:00:00.000 - 00:00:01.000] ?: noop")
