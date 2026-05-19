"""Filename sanitisation and extension validation for uploads.

This tests the sanitisation pipeline only — the actual magic-byte sniff is
covered indirectly because the codepath rejects unknown MIMEs. Driving real
libmagic here would require real audio bytes.
"""
from __future__ import annotations

import pytest

from app.fs import UnsafePathError
from app.routes.uploads import _sanitize_stem, _timestamped_name


def test_sanitize_stem_strips_unsafe_chars():
    assert _sanitize_stem("hello world!") == "hello_world"
    assert _sanitize_stem("/etc/passwd") == "etc_passwd"
    assert _sanitize_stem("...") == "audio"


def test_timestamped_name_keeps_extension(tmp_settings):
    name = _timestamped_name("call.flac", tmp_settings)
    assert name.endswith(".flac")
    assert "call_" in name


def test_timestamped_name_rejects_bad_extension(tmp_settings):
    with pytest.raises(UnsafePathError):
        _timestamped_name("malware.exe", tmp_settings)


@pytest.mark.parametrize("ext", [".wav", ".mp3", ".flac", ".ogg", ".m4a", ".mp4", ".webm", ".aac"])
def test_timestamped_name_accepts_supported_extension(tmp_settings, ext):
    name = _timestamped_name(f"call{ext}", tmp_settings)
    assert name.endswith(ext)


def test_allowed_mimes_includes_aac():
    from app.routes.uploads import ALLOWED_MIMES
    assert "audio/aac" in ALLOWED_MIMES
    assert "audio/x-aac" in ALLOWED_MIMES
    assert "audio/aacp" in ALLOWED_MIMES
