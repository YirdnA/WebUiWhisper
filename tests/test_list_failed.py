"""Dead-letter directory enumeration. Used by the Queue page's Failed section."""
from __future__ import annotations

from app.fs import FAILED_SUBDIR, _parse_error_sidecar, list_failed


def _failed_dir(settings):
    p = settings.calls_dir / FAILED_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def test_empty_failed_dir_returns_empty_list(tmp_settings):
    _failed_dir(tmp_settings)
    assert list_failed(tmp_settings) == []


def test_missing_failed_dir_returns_empty_list(tmp_settings):
    # Don't create the failed/ subdir at all.
    assert list_failed(tmp_settings) == []


def test_audio_with_full_sidecar(tmp_settings):
    fd = _failed_dir(tmp_settings)
    (fd / "boom.flac").write_bytes(b"x" * 100)
    (fd / "boom.flac.error.txt").write_text(
        "first_fail: 2026-05-13T10:00:00\n"
        "last_fail:  2026-05-13T10:05:00\n"
        "attempts:   3\n"
        "last_error: TimeoutError: 3600s\n",
        encoding="utf-8",
    )
    out = list_failed(tmp_settings)
    assert len(out) == 1
    e = out[0]
    assert e["name"] == "boom.flac"
    assert e["size"] == 100
    assert e["attempts"] == 3
    assert "TimeoutError" in e["last_error"]
    assert e["first_fail"] == "2026-05-13T10:00:00"
    assert e["last_fail"] == "2026-05-13T10:05:00"


def test_audio_without_sidecar_uses_placeholder(tmp_settings):
    fd = _failed_dir(tmp_settings)
    (fd / "orphan.flac").write_bytes(b"x")
    out = list_failed(tmp_settings)
    assert len(out) == 1
    e = out[0]
    assert e["name"] == "orphan.flac"
    assert e["last_error"] == "(no sidecar)"
    assert e["attempts"] is None


def test_sidecar_only_no_audio_is_ignored(tmp_settings):
    fd = _failed_dir(tmp_settings)
    (fd / "lonely.flac.error.txt").write_text("last_error: ghost\n", encoding="utf-8")
    assert list_failed(tmp_settings) == []


def test_non_audio_files_skipped(tmp_settings):
    fd = _failed_dir(tmp_settings)
    (fd / "notes.txt").write_text("hello", encoding="utf-8")
    (fd / "image.png").write_bytes(b"\x89PNG")
    assert list_failed(tmp_settings) == []


def test_parse_error_sidecar_multiline_last_error(tmp_settings):
    fd = _failed_dir(tmp_settings)
    p = fd / "x.flac.error.txt"
    p.write_text(
        "first_fail: 2026-05-13T10:00:00\n"
        "last_fail:  2026-05-13T10:05:00\n"
        "attempts:   2\n"
        "last_error: line1\n"
        "line2 continued\n"
        "line3 too\n",
        encoding="utf-8",
    )
    info = _parse_error_sidecar(p)
    assert info["last_error"] == "line1\nline2 continued\nline3 too"
