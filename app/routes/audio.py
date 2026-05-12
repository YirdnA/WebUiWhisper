"""Serve audio files from BACKUP_DIR (post-transcription) or CALLS_DIR
(in-flight) with HTTP Range support so HTML5 <audio> can seek."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from ..config import Settings
from ..deps import current_user, settings_dep
from ..fs import UnsafePathError, validate_filename
from ..rate_limit import limiter

router = APIRouter(prefix="/audio", tags=["audio"])

CHUNK_SIZE = 64 * 1024

MIME_BY_EXT = {
    ".wav":  "audio/wav",
    ".mp3":  "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg":  "audio/ogg",
    ".m4a":  "audio/mp4",
    ".mp4":  "video/mp4",
    ".webm": "video/webm",
}


def _resolve_audio(name: str, settings: Settings) -> Path:
    """Locate the audio file. Watcher moves successful sources from /calls/
    to /backup/, so we check backup first, then calls."""
    validate_filename(name, settings)
    for base in (settings.backup_dir, settings.calls_dir):
        if not base.is_dir():
            continue
        candidate = (base / name).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(name)


_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _parse_range(header: str, size: int) -> tuple[int, int]:
    """Return (start, end_inclusive) for a single Range header. Multi-range not supported."""
    m = _RANGE_RE.match(header.strip())
    if not m:
        raise ValueError("malformed Range header")
    start_s, end_s = m.group(1), m.group(2)
    if start_s == "" and end_s == "":
        raise ValueError("empty Range header")
    if start_s == "":
        # suffix range: last N bytes
        n = int(end_s)
        if n == 0:
            raise ValueError("zero-length suffix")
        start = max(size - n, 0)
        end = size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
        end = min(end, size - 1)
    if start < 0 or start >= size or end < start:
        raise ValueError("unsatisfiable range")
    return start, end


def _file_iter(path: Path, start: int, end: int):
    remaining = end - start + 1
    with open(path, "rb") as fh:
        fh.seek(start)
        while remaining > 0:
            chunk = fh.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/{name}")
@limiter.limit("120/minute")
async def stream_audio(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
):
    try:
        path = _resolve_audio(name, settings)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="audio not found") from None

    size = path.stat().st_size
    mime = MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream")
    common_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=300",
        "Content-Disposition": f'inline; filename="{path.name}"',
    }

    range_header = request.headers.get("range") or request.headers.get("Range")
    if not range_header:
        return StreamingResponse(
            _file_iter(path, 0, size - 1),
            media_type=mime,
            headers={**common_headers, "Content-Length": str(size)},
        )

    try:
        start, end = _parse_range(range_header, size)
    except ValueError:
        return Response(
            status_code=416,
            headers={**common_headers, "Content-Range": f"bytes */{size}"},
        )

    headers = {
        **common_headers,
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Content-Length": str(end - start + 1),
    }
    return StreamingResponse(
        _file_iter(path, start, end),
        status_code=206,
        media_type=mime,
        headers=headers,
    )
