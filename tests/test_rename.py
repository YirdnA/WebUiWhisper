"""Rename route: set / clear / auto-name behaviours."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import enrich as enrich_mod


def _write_transcript(transcripts_dir: Path, name: str = "demo.wav") -> Path:
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
    p = transcripts_dir / f"{name}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


@pytest.fixture()
def client_and_dirs(tmp_settings, monkeypatch):
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
            yield client, tmp_settings, cookie
    finally:
        app.dependency_overrides.pop(settings_dep, None)
        get_settings.cache_clear()


def test_set_display_name(client_and_dirs):
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "demo.wav")
    r = client.post(
        "/transcripts/demo.wav/display-name",
        data={"csrf_token": cookie, "display_name": "Mycology field notes"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    side = settings.transcripts_dir / "demo.wav.display_name"
    assert side.is_file()
    assert "Mycology" in side.read_text()


def test_clear_display_name(client_and_dirs):
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "demo.wav")
    client.post(
        "/transcripts/demo.wav/display-name",
        data={"csrf_token": cookie, "display_name": "Custom"},
        follow_redirects=False,
    )
    r = client.request(
        "DELETE", "/transcripts/demo.wav/display-name",
        data={"csrf_token": cookie},
    )
    assert r.status_code == 200
    assert not (settings.transcripts_dir / "demo.wav.display_name").is_file()


def test_auto_name_from_cached_enrich(client_and_dirs):
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "demo.wav")
    # Cache a sidecar with a title already.
    side = settings.transcripts_dir / "demo.wav.enrich.json"
    side.write_text(json.dumps({
        "schema_version": 1,
        "source": "demo.wav",
        "transcript_sha256": "x",
        "model": "qwen2.5:7b",
        "ran_at": "2026-05-20T00:00:00Z",
        "patterns": {"title": "Sample meeting"},
    }), encoding="utf-8")

    r = client.post(
        "/transcripts/demo.wav/display-name/auto",
        data={"csrf_token": cookie},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Sample meeting"
    assert body["from_cache"] is True


def test_auto_name_runs_single_pattern_when_no_cache(client_and_dirs):
    """When no enrich sidecar exists, the route runs just the title
    pattern through the lock. We mock Ollama."""
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "demo.wav")

    async def fake_chat(self, prompt, json_mode=True):
        return json.dumps({"title": "Generated title"})

    with patch.object(enrich_mod.OllamaClient, "chat", new=fake_chat):
        r = client.post(
            "/transcripts/demo.wav/display-name/auto",
            data={"csrf_token": cookie},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Generated title"
    assert body["from_cache"] is False


def test_display_name_filter_used_in_list(client_and_dirs):
    """After a rename, the list page shows the new name."""
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "demo.wav")
    client.post(
        "/transcripts/demo.wav/display-name",
        data={"csrf_token": cookie, "display_name": "Custom title here"},
        follow_redirects=False,
    )
    r = client.get("/transcripts")
    assert r.status_code == 200
    assert "Custom title here" in r.text


def test_download_filename_uses_display_name(client_and_dirs):
    client, settings, cookie = client_and_dirs
    _write_transcript(settings.transcripts_dir, "demo.wav")
    client.post(
        "/transcripts/demo.wav/display-name",
        data={"csrf_token": cookie, "display_name": "Сонячний день"},
        follow_redirects=False,
    )
    r = client.get("/transcripts/demo.wav/download.txt")
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    # Both ASCII-safe and UTF-8 forms present
    assert "filename=" in cd
    assert "filename*=UTF-8''" in cd
    # ASCII fallback should contain a transliterated Ukrainian form.
    # The exact spelling depends on the map; check for the stable prefix.
    assert "Sonyachn" in cd
