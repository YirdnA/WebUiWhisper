"""Progress route's `_classify` — turns a watcher/whisper log line into a
short phase tag the frontend uses to colour-code the live SSE stream."""
from __future__ import annotations

import pytest

from app.routes.progress import _classify


@pytest.mark.parametrize("line, expected", [
    ("2026-05-14 10:00 [INFO] watcher :: queued: nanotalks_2026.flac", "info"),
    ("2026-05-14 10:01 [INFO] whisper :: transcribing 12 segments", "transcribe"),
    ("2026-05-14 10:02 [INFO] whisper :: faster_whisper invoked", "transcribe"),
    ("2026-05-14 10:30 [INFO] whisper :: diarising audio (pyannote)", "diarize"),
    ("2026-05-14 10:31 [INFO] whisper :: diarization done", "diarize"),
    ("2026-05-14 10:40 [INFO] whisper :: merging segments", "merge"),
    ("2026-05-14 10:42 [INFO] watcher :: ok: file.flac proc=120s", "done"),
    ("2026-05-14 10:50 [ERROR] watcher :: transcription failed", "error"),
    ("2026-05-14 10:51 [INFO] watcher :: sweep removed 1 file", "info"),
])
def test_classify_known_phases(line, expected):
    assert _classify(line) == expected


def test_classify_unknown_returns_empty_string():
    assert _classify("some unrelated noise") == ""
