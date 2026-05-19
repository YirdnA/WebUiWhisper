"""End-to-end tests for the archive/unarchive/delete routes."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _write_transcript(transcripts_dir: Path, name: str = "demo.wav") -> Path:
    """Drop a minimal valid `{name}.json` into the live tier."""
    payload = {
        "source_file": name,
        "language": "en",
        "language_confidence": 0.99,
        "duration_sec": 10.0,
        "processing_sec": 2.0,
        "model_used": "large-v3",
        "segments": [
            {"speaker": "spk_0", "start_time": "00:00:00.000",
             "end_time": "00:00:10.000", "start_sec": 0.0, "end_sec": 10.0,
             "text": "Hello world."},
        ],
    }
    path = transcripts_dir / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@pytest.fixture()
def client_and_dirs(tmp_settings, monkeypatch):
    """Spin up the real app against `tmp_settings`. Returns (client, settings).

    Strategy: set env vars + clear the get_settings LRU cache *before* the
    lifespan runs (which happens at `with TestClient(app):` entry). The
    lifespan calls `get_settings()` directly (not the FastAPI dependency),
    so an env-var path is the only way to swap its view of the world.
    Dependency_overrides are also wired for any code that calls the dep
    fresh per-request.
    """
    monkeypatch.setenv("TRANSCRIPTS_DIR", str(tmp_settings.transcripts_dir))
    monkeypatch.setenv("CALLS_DIR", str(tmp_settings.calls_dir))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_settings.backup_dir))
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_settings.state_db_path))
    monkeypatch.setenv("LOG_DIR", str(tmp_settings.log_dir))
    monkeypatch.setenv("SESSION_SECRET", tmp_settings.session_secret)
    monkeypatch.setenv("DEV_FALLBACK_USER", "tester")

    from app.config import get_settings
    get_settings.cache_clear()

    from app.main import app
    from app.deps import settings_dep

    app.dependency_overrides[settings_dep] = lambda: tmp_settings
    try:
        with TestClient(app, base_url="https://testserver") as client:
            client.headers.update({"Remote-User": "tester"})
            r = client.get("/transcripts")
            assert r.status_code == 200, r.text
            cookie = client.cookies.get("ww_csrf")
            assert cookie, "CSRF cookie should have been set by middleware"
            yield client, tmp_settings, cookie
    finally:
        app.dependency_overrides.pop(settings_dep, None)
        get_settings.cache_clear()


def _post(client, cookie, url, extra=None):
    data = {"csrf_token": cookie}
    if extra:
        data.update(extra)
    return client.post(url, data=data, follow_redirects=False)


def test_archive_moves_files_to_archive_dir(client_and_dirs):
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "demo.wav")

    r = _post(client, cookie, "/transcripts/demo.wav/archive")
    assert r.status_code == 303

    archive_dir = settings.transcripts_dir / "archive"
    assert (archive_dir / "demo.wav.json").is_file()
    assert not (settings.transcripts_dir / "demo.wav.json").is_file()


def test_unarchive_restores_files(client_and_dirs):
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "demo.wav")
    _post(client, cookie, "/transcripts/demo.wav/archive")

    r = _post(client, cookie, "/transcripts/demo.wav/unarchive")
    assert r.status_code == 303

    assert (settings.transcripts_dir / "demo.wav.json").is_file()
    assert not (settings.transcripts_dir / "archive" / "demo.wav.json").is_file()


def test_delete_refuses_live_transcript(client_and_dirs):
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "demo.wav")

    r = _post(client, cookie, "/transcripts/demo.wav/delete",
              extra={"confirm": "demo"})
    assert r.status_code == 400
    # File must still exist
    assert (settings.transcripts_dir / "demo.wav.json").is_file()


def test_delete_requires_typed_confirm(client_and_dirs):
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "demo.wav")
    _post(client, cookie, "/transcripts/demo.wav/archive")

    # Wrong confirm value
    r = _post(client, cookie, "/transcripts/demo.wav/delete",
              extra={"confirm": "wrong"})
    assert r.status_code == 400
    assert (settings.transcripts_dir / "archive" / "demo.wav.json").is_file()


def test_delete_archived_with_correct_confirm_removes_file(client_and_dirs):
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "demo.wav")
    _post(client, cookie, "/transcripts/demo.wav/archive")

    # Stem is "demo" (basename without extension)
    r = _post(client, cookie, "/transcripts/demo.wav/delete",
              extra={"confirm": "demo"})
    assert r.status_code == 303
    assert not (settings.transcripts_dir / "archive" / "demo.wav.json").is_file()


def test_bulk_delete_refused_when_any_live(client_and_dirs):
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "live.wav")
    _write_transcript(settings.transcripts_dir, "arch.wav")
    _post(client, cookie, "/transcripts/arch.wav/archive")

    r = client.post(
        "/transcripts/bulk",
        data={
            "csrf_token": cookie,
            "action": "delete",
            "names": ["live.wav", "arch.wav"],
        },
        follow_redirects=False,
    )
    assert r.status_code == 400
    # Both files still exist
    assert (settings.transcripts_dir / "live.wav.json").is_file()
    assert (settings.transcripts_dir / "archive" / "arch.wav.json").is_file()


def test_list_shows_archive_tab_with_counts(client_and_dirs):
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "a.wav")
    _write_transcript(settings.transcripts_dir, "b.wav")
    _post(client, cookie, "/transcripts/b.wav/archive")

    r = client.get("/transcripts")
    body = r.text
    # Live shows 1 transcript, archive shows 1.
    assert re.search(r"Live\s*<span class=\"count\">\(1\)", body)
    assert re.search(r"Archived\s*<span class=\"count\">\(1\)", body)

    r = client.get("/transcripts?view=archived")
    assert "b.wav" in r.text or "b (" in r.text  # display filter falls back to pretty


def test_inline_download_returns_txt(client_and_dirs):
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "demo.wav")
    r = client.get("/transcripts/demo.wav/download.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    # Content-Disposition should carry both ASCII and UTF-8 forms.
    cd = r.headers["content-disposition"]
    assert "filename=" in cd
    assert "filename*=UTF-8''" in cd
