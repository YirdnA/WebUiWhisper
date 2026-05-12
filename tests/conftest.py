from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `app` importable when running pytest from the repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from app.config import Settings


@pytest.fixture()
def tmp_settings(tmp_path: Path) -> Settings:
    calls = tmp_path / "calls"
    transcripts = tmp_path / "transcripts"
    backup = tmp_path / "backup"
    state = tmp_path / "state"
    for d in (calls, transcripts, backup, state):
        d.mkdir(parents=True, exist_ok=True)
    os.environ["SESSION_SECRET"] = "test-secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    return Settings(
        whisper_api_url="http://upstream.test",
        calls_dir=calls,
        transcripts_dir=transcripts,
        backup_dir=backup,
        state_db_path=state / "state.db",
        log_dir=tmp_path,
        session_secret="test-secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    )
