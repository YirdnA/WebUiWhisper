"""Content-Disposition tests covering Cyrillic + transliteration paths."""
from __future__ import annotations

from urllib.parse import unquote

import pytest

from app.display_name import (
    clear_display_name,
    sanitize_filename_ascii,
    write_display_name,
)


def test_sanitize_ascii_passthrough():
    assert sanitize_filename_ascii("Hello World") == "Hello World"
    assert sanitize_filename_ascii("foo_bar-1") == "foo_bar-1"


def test_sanitize_strips_emoji_and_unsafe():
    # Emoji + bang dropped; consecutive whitespace collapses to single.
    assert sanitize_filename_ascii("hi 🎤 there!") == "hi there"


def test_sanitize_transliterates_russian():
    out = sanitize_filename_ascii("Грибы и место")
    # Expected: Griby i mesto (no exotic chars)
    assert out == "Griby i mesto"


def test_sanitize_transliterates_ukrainian():
    out = sanitize_filename_ascii("Нанотолкс — їжак")
    # Expected: "Nanotolks  yizhak" (em-dash + space collapse)
    assert out.startswith("Nanotolks")
    assert "yizhak" in out


def test_sanitize_truncates_to_100():
    long = "a" * 250
    out = sanitize_filename_ascii(long)
    assert len(out) == 100


def test_sanitize_empty_returns_empty():
    assert sanitize_filename_ascii("") == ""
    assert sanitize_filename_ascii("...") == ""


def test_display_name_roundtrip(tmp_settings):
    write_display_name("demo.wav", "Hello World", tmp_settings)
    from app.display_name import read_display_name
    assert read_display_name("demo.wav", tmp_settings) == "Hello World"
    clear_display_name("demo.wav", tmp_settings)
    assert read_display_name("demo.wav", tmp_settings) is None


def test_display_name_empty_clears(tmp_settings):
    write_display_name("demo.wav", "Hello", tmp_settings)
    write_display_name("demo.wav", "", tmp_settings)
    from app.display_name import read_display_name
    assert read_display_name("demo.wav", tmp_settings) is None
