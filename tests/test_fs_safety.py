"""Path traversal and filename safety."""
from __future__ import annotations

import pytest

from app.fs import UnsafePathError, safe_join, safe_transcript_path, validate_filename


def test_simple_filename_ok(tmp_settings):
    assert validate_filename("foo.flac", tmp_settings) == "foo.flac"
    assert validate_filename("call_2026-05-12.wav", tmp_settings) == "call_2026-05-12.wav"


@pytest.mark.parametrize("bad", [
    "../etc/passwd",
    "..",
    "/etc/passwd",
    ".hidden.flac",
    "foo.exe",
    "foo",                # no extension
    "foo.txt",            # not audio
    "spaces are not allowed.flac",
    "",
    "a" * 250 + ".flac",  # too long
])
def test_validate_rejects(tmp_settings, bad):
    with pytest.raises(UnsafePathError):
        validate_filename(bad, tmp_settings)


def test_safe_join_inside_base(tmp_settings):
    p = safe_join(tmp_settings.calls_dir, "good.flac", tmp_settings)
    assert p.parent == tmp_settings.calls_dir.resolve()


def test_safe_join_blocks_symlink_escape(tmp_settings, tmp_path):
    # Plant a symlink inside calls/ that points outside.
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evil.flac").write_bytes(b"")
    link = tmp_settings.calls_dir / "evil.flac"
    link.symlink_to(outside / "evil.flac")
    with pytest.raises(UnsafePathError):
        safe_join(tmp_settings.calls_dir, "evil.flac", tmp_settings)


def test_safe_transcript_path_only_json_or_txt(tmp_settings):
    p = safe_transcript_path(tmp_settings.transcripts_dir, "foo.flac.json")
    assert str(p).endswith("foo.flac.json")
    p = safe_transcript_path(tmp_settings.transcripts_dir, "foo.flac.txt")
    assert str(p).endswith("foo.flac.txt")
    with pytest.raises(UnsafePathError):
        safe_transcript_path(tmp_settings.transcripts_dir, "foo.flac.srt")
    with pytest.raises(UnsafePathError):
        safe_transcript_path(tmp_settings.transcripts_dir, "../foo.json")
    with pytest.raises(UnsafePathError):
        safe_transcript_path(tmp_settings.transcripts_dir, "/etc/passwd.json")
