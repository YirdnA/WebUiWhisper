from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    whisper_api_url: str = "http://whisper:8000"

    calls_dir: Path = Path("/calls")
    transcripts_dir: Path = Path("/transcripts")
    backup_dir: Path = Path("/backup")
    state_db_path: Path = Path("/var/lib/webuiwhisper/state.db")
    log_dir: Path = Path("/transcripts")

    session_secret: str = "replace-me-with-a-real-secret"
    remote_user_header: str = "Remote-User"
    trust_remote_user: bool = True
    # If set, requests without a Remote-User header fall back to this name.
    # Intended for local dev only — leave empty in production where Apache
    # always supplies Remote-User.
    dev_fallback_user: str = ""

    max_upload_bytes: int = 500 * 1024 * 1024
    rate_reads_per_min: int = 60
    rate_writes_per_min: int = 10

    login_fails_before_lockout: int = 5
    login_lockout_minutes: int = 15

    default_model: str = "large-v3"

    allowed_audio_exts: tuple[str, ...] = Field(
        default=(".wav", ".mp3", ".flac", ".ogg", ".m4a", ".mp4", ".webm")
    )

    @property
    def audit_log_path(self) -> Path:
        return self.log_dir / "webuiwhisper-audit.log"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
