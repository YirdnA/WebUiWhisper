"""Watcher.log tail parser used by the Queue page to decide which files
are currently being transcribed."""
from __future__ import annotations

from pathlib import Path

from app.fs import _extract_filename, read_inflight_state


# Each tuple is (full log line, marker that matches, expected filename).
EXTRACT_CASES = [
    ("2026-05-14 10:00 [INFO] watcher :: queued: foo.flac",
     " :: queued: ", "foo.flac"),
    ("2026-05-14 10:01 [INFO] watcher :: ok: foo.flac model=large-v3 wait=4.0s proc=120s lang=uk speakers=2",
     " :: ok: ", "foo.flac"),
    ("2026-05-14 10:02 [INFO] watcher :: retry 1/3 (next in 60s): doomed.wav",
     " :: retry ", "doomed.wav"),
    ("2026-05-14 10:03 [ERROR] watcher :: transcription failed: bad.flac",
     " :: transcription failed: ", "bad.flac"),
    ("2026-05-14 10:04 [ERROR] watcher :: DEAD-LETTER (after 3 attempts): doomed.wav -> /calls/failed/doomed.wav",
     " :: DEAD-LETTER ", "doomed.wav"),
    ("2026-05-14 10:05 [INFO] watcher :: skip (already transcribed): 1.wav",
     " :: skip (already transcribed): ", "1.wav"),
]


def test_extract_filename_recognises_every_shape():
    for line, marker, expected in EXTRACT_CASES:
        assert _extract_filename(line, marker) == expected, line


def test_inflight_when_no_terminal_event(tmp_path):
    log = tmp_path / "watcher.log"
    log.write_text(
        "2026-05-14 10:00 [INFO] watcher :: queued: a.flac\n",
        encoding="utf-8",
    )
    assert read_inflight_state(log) == {"a.flac": "queued"}


def test_not_inflight_after_ok(tmp_path):
    log = tmp_path / "watcher.log"
    log.write_text(
        "2026-05-14 10:00 [INFO] watcher :: queued: a.flac\n"
        "2026-05-14 10:01 [INFO] watcher :: ok: a.flac model=large-v3 wait=4s\n",
        encoding="utf-8",
    )
    assert read_inflight_state(log) == {}


def test_not_inflight_after_transcription_failed(tmp_path):
    log = tmp_path / "watcher.log"
    log.write_text(
        "2026-05-14 10:00 [INFO] watcher :: queued: a.flac\n"
        "2026-05-14 10:01 [ERROR] watcher :: transcription failed: a.flac\n",
        encoding="utf-8",
    )
    assert read_inflight_state(log) == {}


def test_not_inflight_after_deadletter(tmp_path):
    log = tmp_path / "watcher.log"
    log.write_text(
        "2026-05-14 10:00 [INFO] watcher :: queued: a.flac\n"
        "2026-05-14 10:01 [ERROR] watcher :: DEAD-LETTER (after 3 attempts): a.flac -> /calls/failed/a.flac\n",
        encoding="utf-8",
    )
    assert read_inflight_state(log) == {}


def test_inflight_when_only_retry_seen(tmp_path):
    """A `retry` line means the file was re-enqueued; treat as in-flight."""
    log = tmp_path / "watcher.log"
    log.write_text(
        "2026-05-14 10:00 [INFO] watcher :: queued: a.flac\n"
        "2026-05-14 10:01 [WARNING] watcher :: retry 1/3 (next in 60s): a.flac\n",
        encoding="utf-8",
    )
    assert read_inflight_state(log) == {"a.flac": "retry"}


def test_multiple_files_tracked_independently(tmp_path):
    log = tmp_path / "watcher.log"
    log.write_text(
        "2026-05-14 10:00 [INFO] watcher :: queued: a.flac\n"
        "2026-05-14 10:01 [INFO] watcher :: ok: a.flac model=...\n"
        "2026-05-14 10:02 [INFO] watcher :: queued: b.flac\n",
        encoding="utf-8",
    )
    assert read_inflight_state(log) == {"b.flac": "queued"}


def test_missing_file_returns_empty(tmp_path):
    assert read_inflight_state(tmp_path / "missing.log") == {}


def test_tail_window_only_recent_lines(tmp_path):
    """A long log should only have its tail scanned; old `ok:` events outside
    the window can be ignored without affecting the result."""
    log = tmp_path / "watcher.log"
    # Fill 200 KiB of noise before the only line that matters.
    log.write_text(
        ("# noise " * 200 + "\n") * 200
        + "2026-05-14 10:00 [INFO] watcher :: queued: tail.flac\n",
        encoding="utf-8",
    )
    assert read_inflight_state(log, tail_bytes=4096) == {"tail.flac": "queued"}
