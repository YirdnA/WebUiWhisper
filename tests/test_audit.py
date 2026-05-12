from __future__ import annotations

import pytest

from app.audit import recent, record
from app.db import init_db


@pytest.mark.asyncio
async def test_record_writes_file_and_db(tmp_settings):
    await init_db(tmp_settings)
    await record("upload", user="alice", ip="1.2.3.4", target="x.flac", ok=True,
                 settings=tmp_settings)
    # File line
    text = tmp_settings.audit_log_path.read_text(encoding="utf-8").strip()
    assert "alice" in text and "x.flac" in text and "upload" in text
    # DB row
    rows = await recent(settings=tmp_settings)
    assert rows and rows[0]["action"] == "upload"
    assert rows[0]["target"] == "x.flac"
    assert rows[0]["user"] == "alice"
    assert rows[0]["ip"] == "1.2.3.4"


@pytest.mark.asyncio
async def test_record_failure_ok_false(tmp_settings):
    await init_db(tmp_settings)
    await record("upload-rejected", user="bob", ip="9.9.9.9", target="z.flac",
                 ok=False, extra={"mime": "text/plain"}, settings=tmp_settings)
    rows = await recent(settings=tmp_settings)
    assert rows[0]["ok"] == 0
