"""Inline editor's versioning: each save copies the live JSON to a
{name}.json.v{N} sidecar before writing the new content."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.editor import archive_current, next_version


def _write_live(transcripts_dir: Path, name: str, content: str = '{"segments": []}'):
    (transcripts_dir / f"{name}.json").write_text(content, encoding="utf-8")


def test_next_version_starts_at_one(tmp_path):
    _write_live(tmp_path, "rec")
    assert next_version(tmp_path, "rec") == 1


def test_archive_current_writes_v1_and_preserves_live(tmp_path):
    _write_live(tmp_path, "rec", '{"orig": 1}')
    dst = archive_current(tmp_path, "rec")
    assert dst == tmp_path / "rec.json.v1"
    assert dst.read_text() == '{"orig": 1}'
    # Live JSON is untouched.
    assert (tmp_path / "rec.json").read_text() == '{"orig": 1}'


def test_archive_current_increments_versions(tmp_path):
    _write_live(tmp_path, "rec", '{"v": 1}')
    archive_current(tmp_path, "rec")          # writes v1
    (tmp_path / "rec.json").write_text('{"v": 2}', encoding="utf-8")
    archive_current(tmp_path, "rec")          # writes v2
    assert (tmp_path / "rec.json.v1").exists()
    assert (tmp_path / "rec.json.v2").read_text() == '{"v": 2}'
    assert next_version(tmp_path, "rec") == 3


def test_archive_current_returns_none_when_no_live(tmp_path):
    assert archive_current(tmp_path, "missing") is None
