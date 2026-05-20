"""Regex tests for the audio-basename validator used across routes.

The user uploads audio with all sorts of filenames; common cases include
spaces, commas, parentheses (e.g. "21 Apr, 17.32 andriytg.wav"). The
regex must accept those while still rejecting traversal-style names."""
from __future__ import annotations

import re

import pytest

from app.fs import _NAME_RE


VALID = [
    "demo.wav",
    "nanotalks_2026-05-12_19-40-56.flac",
    "21 Apr, 17.32 andriytg.wav",       # the user's case
    "Some File (v2).mp3",
    "a.b.c.json",
    "file-with-dash_and_underscore.wav",
]

INVALID = [
    "",                          # empty
    ".hidden.wav",               # leading dot
    "../etc/passwd",             # traversal
    "name/with/slash.wav",       # slash
    "name\\with\\back.wav",      # backslash
    "file..json",                # consecutive dots
    "a" * 250 + ".wav",          # too long
    "name\nwith\nnewline.wav",   # control char
]


@pytest.mark.parametrize("name", VALID)
def test_valid_names_match(name):
    assert _NAME_RE.match(name), f"should accept {name!r}"


@pytest.mark.parametrize("name", INVALID)
def test_invalid_names_rejected(name):
    assert not _NAME_RE.match(name), f"should reject {name!r}"


def test_safe_transcript_path_accepts_space_comma_form():
    from app.fs import safe_transcript_path
    # Should not raise — produces a Path under the base dir.
    base = __import__("pathlib").Path("/tmp")
    p = safe_transcript_path(base, "21 Apr, 17.32 andriytg.wav.json")
    assert str(p).endswith("21 Apr, 17.32 andriytg.wav.json")
