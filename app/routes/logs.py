"""Operator log-tail page. Two tabs: whisper.log and watcher.log, streamed
via SSE. Reuses `_tail_stream` from `app/routes/progress.py`."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from ..config import Settings
from ..deps import current_user, settings_dep
from ..rate_limit import limiter
from .progress import _tail_stream

router = APIRouter(prefix="/logs", tags=["logs"])

# Hard allowlist. Anything else returns 404 — no path traversal possible.
ALLOWED_FILES = {"whisper", "watcher"}


def _validate_file(name: str | None) -> str:
    if not name or name not in ALLOWED_FILES:
        raise HTTPException(status_code=404, detail="unknown log file")
    return name


def _templates(request: Request):
    return request.app.state.templates


@router.get("", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def logs_view(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    file: str = "whisper",
):
    active = file if file in ALLOWED_FILES else "whisper"
    return _templates(request).TemplateResponse(
        request, "logs/index.html",
        {
            "user": user,
            "page": "logs",
            "active": active,
            "files": sorted(ALLOWED_FILES),
        },
    )


@router.get("/{file}/stream")
@limiter.limit("30/minute")
async def logs_stream(
    file: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
):
    name = _validate_file(file)
    log_path = settings.log_dir / f"{name}.log"
    return StreamingResponse(
        _tail_stream(log_path, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
