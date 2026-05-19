"""Hard allowlist on the /logs/{file}/stream route — no path traversal possible."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routes.logs import ALLOWED_FILES, _validate_file


@pytest.mark.parametrize("name", sorted(ALLOWED_FILES))
def test_accepts_listed_files(name):
    assert _validate_file(name) == name


@pytest.mark.parametrize("name", [
    "", "Whisper", "watcher.log", "../etc/passwd", "/var/log/syslog",
    "..", "whisper/../watcher", "whisper\x00", "evil",
])
def test_rejects_everything_else(name):
    with pytest.raises(HTTPException) as ei:
        _validate_file(name)
    assert ei.value.status_code == 404


def test_rejects_none():
    with pytest.raises(HTTPException):
        _validate_file(None)
