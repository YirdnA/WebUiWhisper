"""Display name beautifier used in the detail-page title (`_pretty_name`)
and the list-row column (`_stem`)."""
from __future__ import annotations

from app.main import _pretty_name, _stem


def test_pretty_name_typical_jibri_filename():
    assert _pretty_name("nanotalks_2026-05-12_19-40-56.flac") == \
        "nanotalks (2026-05-12 19:40:56)"


def test_pretty_name_works_without_extension():
    assert _pretty_name("foo_2026-01-01_00-00-00") == "foo (2026-01-01 00:00:00)"


def test_pretty_name_keeps_stem_with_underscores():
    assert _pretty_name("very_long_room_name_2026-05-12_19-40-56.flac") == \
        "very_long_room_name (2026-05-12 19:40:56)"


def test_pretty_name_returns_unchanged_when_pattern_does_not_match():
    assert _pretty_name("1.wav") == "1.wav"
    assert _pretty_name("hand-named.flac") == "hand-named.flac"
    assert _pretty_name("") == ""


def test_stem_strips_timestamp_and_extension():
    assert _stem("nanotalks_2026-05-12_19-40-56.flac") == "nanotalks"
    assert _stem("very_long_room_2026-05-12_19-40-56.flac") == "very_long_room"


def test_stem_falls_back_to_basename_when_no_timestamp():
    assert _stem("1.wav") == "1"
    assert _stem("hand-named.flac") == "hand-named"
    assert _stem("no-extension") == "no-extension"
