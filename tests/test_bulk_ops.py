"""Bulk delete + archive operations — file-system side-effects of one
transcript at a time. The HTTP route just iterates these helpers."""
from __future__ import annotations

from pathlib import Path

from app.routes.bulk import _archive_one, _delete_one


def _make_transcript(transcripts_dir: Path, backup_dir: Path, name: str,
                     *, audio: bool = True, versions: int = 0):
    (transcripts_dir / f"{name}.json").write_text('{"segments": []}', encoding="utf-8")
    (transcripts_dir / f"{name}.txt").write_text("hello world", encoding="utf-8")
    for i in range(1, versions + 1):
        (transcripts_dir / f"{name}.json.v{i}").write_text(
            f'{{"v": {i}}}', encoding="utf-8")
    if audio:
        (backup_dir / name).write_bytes(b"RIFF" + b"\x00" * 60)


def test_delete_one_removes_live_and_versions_and_audio(tmp_settings):
    _make_transcript(tmp_settings.transcripts_dir, tmp_settings.backup_dir,
                     "rec.flac", versions=2)
    res = _delete_one("rec.flac", tmp_settings)
    assert res == {"transcripts_removed": 4, "audio_removed": 1}
    assert not (tmp_settings.transcripts_dir / "rec.flac.json").exists()
    assert not (tmp_settings.transcripts_dir / "rec.flac.json.v1").exists()
    assert not (tmp_settings.transcripts_dir / "rec.flac.json.v2").exists()
    assert not (tmp_settings.backup_dir / "rec.flac").exists()


def test_delete_one_noop_for_missing_transcript(tmp_settings):
    res = _delete_one("does-not-exist.wav", tmp_settings)
    assert res == {"transcripts_removed": 0, "audio_removed": 0}


def test_archive_one_moves_files_into_archive_subdir(tmp_settings):
    _make_transcript(tmp_settings.transcripts_dir, tmp_settings.backup_dir,
                     "rec.flac")
    res = _archive_one("rec.flac", tmp_settings)
    assert res == {"transcripts_archived": 2, "audio_archived": 1}
    arch = tmp_settings.transcripts_dir / "archive"
    assert (arch / "rec.flac.json").is_file()
    assert (arch / "rec.flac.txt").is_file()
    assert (arch / "audio" / "rec.flac").is_file()
    # Originals are gone.
    assert not (tmp_settings.transcripts_dir / "rec.flac.json").exists()
    assert not (tmp_settings.backup_dir / "rec.flac").exists()
