"""Rediarize is fire-and-forget: the HTTP submit handler spawns `_run`,
which calls the whisper client and writes start/ok/fail audit rows.
Test exercises both the success and the WhisperClientError paths."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.routes.rediarize import _run
from app.whisper_client import WhisperClientError


@pytest.mark.asyncio
async def test_run_records_start_and_ok_on_success():
    client = AsyncMock()
    client.rediarize.return_value = {
        "segments": [{"speaker": "S0"}, {"speaker": "S1"}, {"speaker": "S0"}],
    }
    hints = {"num_speakers": 2, "min_speakers": None, "max_speakers": None}

    with patch("app.routes.rediarize.audit_record", new=AsyncMock()) as rec:
        await _run(client, "rec.flac", hints, user="alice", ip="1.2.3.4")

    client.rediarize.assert_awaited_once_with(
        "rec.flac", num_speakers=2, min_speakers=None, max_speakers=None)
    actions = [call.args[0] for call in rec.await_args_list]
    assert actions == ["rediarize-start", "rediarize-ok"]
    # Speaker count derived from unique speakers in segments.
    ok_kwargs = rec.await_args_list[1].kwargs
    assert ok_kwargs["extra"] == {"speakers": 2}
    assert ok_kwargs["target"] == "rec.flac"
    assert ok_kwargs["ok"] is True


@pytest.mark.asyncio
async def test_run_records_fail_on_whisper_client_error():
    client = AsyncMock()
    client.rediarize.side_effect = WhisperClientError("upstream 503")

    with patch("app.routes.rediarize.audit_record", new=AsyncMock()) as rec:
        await _run(client, "rec.flac", {}, user="alice", ip="1.2.3.4")

    actions = [call.args[0] for call in rec.await_args_list]
    assert actions == ["rediarize-start", "rediarize-fail"]
    fail_kwargs = rec.await_args_list[1].kwargs
    assert fail_kwargs["ok"] is False
    assert "upstream 503" in fail_kwargs["extra"]["err"]
