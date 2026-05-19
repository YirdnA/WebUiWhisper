"""Server-Sent Events tail of the whisper service's log file.

Connects to `{TRANSCRIPTS_DIR}/whisper.log`, tracks a byte offset, polls every
POLL_SEC for new content and streams it as SSE. Lines are classified by
substring (`transcribe`, `diariz`, `merge`, `done`) so the frontend can pick
out the phase without parsing.

The route emits SSE comments as keep-alives so the connection survives
Apache's ProxyTimeout.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..config import Settings
from ..deps import current_user, settings_dep
from ..rate_limit import limiter

router = APIRouter(prefix="/progress", tags=["progress"])

POLL_SEC = 2.0
KEEPALIVE_SEC = 25.0       # < Apache's ProxyTimeout (600 here, but be defensive)
MAX_TAIL_BYTES = 16 * 1024  # initial chunk shown on connect


def _classify(line: str) -> str:
    """Lowercase phase tag for the frontend. Empty if unmatched."""
    s = line.lower()
    if "done " in s or " ok:" in s or " ok " in s:
        return "done"
    if "diaris" in s or "diariz" in s:
        return "diarize"
    if "transcrib" in s or "faster_whisper" in s:
        return "transcribe"
    if "merg" in s:
        return "merge"
    if "queued" in s or "sweep" in s or "starting" in s:
        return "info"
    if "error" in s or "fail" in s or "exception" in s:
        return "error"
    return ""


def _sse(event: str | None, data: str) -> bytes:
    """Format an SSE record. Each `data:` line is a separate frame line."""
    parts = []
    if event:
        parts.append(f"event: {event}")
    for line in data.splitlines() or [""]:
        parts.append(f"data: {line}")
    parts.append("")  # terminator
    parts.append("")
    return ("\n".join(parts)).encode("utf-8")


async def _tail_stream(log_path: Path, request: Request) -> AsyncIterator[bytes]:
    """SSE generator that streams new content appended to `log_path`.

    Module-public — reused by `app/routes/logs.py` for the operator log-tail
    page. Emits an initial `hello` event, one `log` event per new non-empty
    line (with a `phase` tag from `_classify`), keepalive comments every
    KEEPALIVE_SEC, and an `error` event when the file goes missing."""
    # Initial state: tell client where we are.
    yield _sse("hello", json.dumps({"file": str(log_path), "ts": time.time()}))

    if not log_path.is_file():
        yield _sse("error", f"log file not present yet: {log_path}")
        # Wait politely; the watcher may create it once it does work.
        while True:
            if await request.is_disconnected():
                return
            await asyncio.sleep(POLL_SEC)
            if log_path.is_file():
                break

    # Start at the last MAX_TAIL_BYTES so the client sees recent context.
    size = log_path.stat().st_size
    offset = max(0, size - MAX_TAIL_BYTES)
    last_keepalive = time.monotonic()

    while True:
        if await request.is_disconnected():
            return

        try:
            size = log_path.stat().st_size
        except FileNotFoundError:
            yield _sse("error", "log file disappeared")
            await asyncio.sleep(POLL_SEC)
            continue

        # Handle log rotation: file shrank or got replaced.
        if size < offset:
            offset = 0

        if size > offset:
            try:
                with open(log_path, "rb") as fh:
                    fh.seek(offset)
                    chunk = fh.read(size - offset)
                    offset = size
            except OSError:
                await asyncio.sleep(POLL_SEC)
                continue
            text = chunk.decode("utf-8", errors="replace")
            for line in text.splitlines():
                if not line.strip():
                    continue
                phase = _classify(line)
                yield _sse(
                    "log",
                    json.dumps({"text": line, "phase": phase, "ts": time.time()}),
                )
            last_keepalive = time.monotonic()

        if time.monotonic() - last_keepalive > KEEPALIVE_SEC:
            yield b": keepalive\n\n"
            last_keepalive = time.monotonic()

        await asyncio.sleep(POLL_SEC)


@router.get("/stream")
@limiter.limit("30/minute")
async def progress_stream(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
):
    log_path = settings.log_dir / "whisper.log"
    return StreamingResponse(
        _tail_stream(log_path, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
