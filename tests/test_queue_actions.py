"""Retry / Discard helpers on the Queue page."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.fs import FAILED_SUBDIR
from app.routes.queue import _discard_one, _retry_one, _safe_name


def _stage(settings, name: str, *, with_sidecar: bool = True):
    fd = settings.calls_dir / FAILED_SUBDIR
    fd.mkdir(parents=True, exist_ok=True)
    (fd / name).write_bytes(b"x" * 32)
    if with_sidecar:
        (fd / f"{name}.error.txt").write_text("last_error: boom\n", encoding="utf-8")


def test_safe_name_accepts_typical_filename():
    assert _safe_name("nanotalks_2026-05-12_19-40-56.flac") == \
        "nanotalks_2026-05-12_19-40-56.flac"


@pytest.mark.parametrize("bad", ["", "../etc/passwd", "../shadow.flac",
                                  ".hidden.flac", "spaces in name.flac",
                                  "/abs.flac"])
def test_safe_name_rejects_unsafe(bad):
    with pytest.raises(HTTPException):
        _safe_name(bad)


def test_retry_moves_file_out_and_removes_sidecar(tmp_settings):
    _stage(tmp_settings, "boom.flac")
    info = _retry_one("boom.flac", tmp_settings)
    assert info["moved_to"].endswith("/calls/boom.flac") or \
           info["moved_to"].endswith("boom.flac")
    assert (tmp_settings.calls_dir / "boom.flac").is_file()
    assert not (tmp_settings.calls_dir / FAILED_SUBDIR / "boom.flac").exists()
    assert not (tmp_settings.calls_dir / FAILED_SUBDIR / "boom.flac.error.txt").exists()


def test_retry_handles_missing_sidecar(tmp_settings):
    _stage(tmp_settings, "lonely.flac", with_sidecar=False)
    _retry_one("lonely.flac", tmp_settings)
    assert (tmp_settings.calls_dir / "lonely.flac").is_file()


def test_retry_404_when_failed_entry_missing(tmp_settings):
    (tmp_settings.calls_dir / FAILED_SUBDIR).mkdir(parents=True, exist_ok=True)
    with pytest.raises(HTTPException) as ei:
        _retry_one("ghost.flac", tmp_settings)
    assert ei.value.status_code == 404


def test_retry_409_when_destination_already_exists(tmp_settings):
    _stage(tmp_settings, "dup.flac")
    (tmp_settings.calls_dir / "dup.flac").write_bytes(b"already-here")
    with pytest.raises(HTTPException) as ei:
        _retry_one("dup.flac", tmp_settings)
    assert ei.value.status_code == 409


def test_discard_removes_both_files(tmp_settings):
    _stage(tmp_settings, "boom.flac")
    info = _discard_one("boom.flac", tmp_settings)
    assert len(info["removed"]) == 2
    assert not (tmp_settings.calls_dir / FAILED_SUBDIR / "boom.flac").exists()
    assert not (tmp_settings.calls_dir / FAILED_SUBDIR / "boom.flac.error.txt").exists()


def test_discard_handles_missing_sidecar(tmp_settings):
    _stage(tmp_settings, "lonely.flac", with_sidecar=False)
    info = _discard_one("lonely.flac", tmp_settings)
    assert info["removed"] == [
        str(tmp_settings.calls_dir / FAILED_SUBDIR / "lonely.flac")
    ]


def test_discard_404_when_nothing_to_remove(tmp_settings):
    (tmp_settings.calls_dir / FAILED_SUBDIR).mkdir(parents=True, exist_ok=True)
    with pytest.raises(HTTPException) as ei:
        _discard_one("ghost.flac", tmp_settings)
    assert ei.value.status_code == 404
