"""Queue page: pending / in-flight / failed (dead-letter), plus retry
and discard actions for failed entries."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..audit import record as audit_record
from ..config import Settings
from ..deps import current_user, require_csrf, settings_dep
from ..fs import (
    FAILED_SUBDIR,
    list_failed,
    list_queue,
    read_inflight_state,
)
from ..rate_limit import limiter

router = APIRouter(prefix="/queue", tags=["queue"])

log = logging.getLogger("webuiwhisper.queue")

_NAME_RE = re.compile(r"^(?!\.)(?!.*\.\.)[A-Za-z0-9_.\-, ()]{1,210}$")


def _safe_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"bad name: {name!r}")
    return name


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "-"
    return request.client.host


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _retry_one(name: str, settings: Settings) -> dict:
    """Move /calls/failed/{name} → /calls/{name}; remove the .error.txt
    sidecar. Returns {moved_to} on success, raises on failure."""
    name = _safe_name(name)
    failed_dir = settings.calls_dir / FAILED_SUBDIR
    src = failed_dir / name
    dst = settings.calls_dir / name
    sidecar = failed_dir / f"{name}.error.txt"
    if not src.is_file():
        raise HTTPException(status_code=404, detail="failed entry not found")
    if dst.exists():
        raise HTTPException(status_code=409,
                            detail="a file with that name already exists in /calls/")
    src.rename(dst)
    try:
        sidecar.unlink()
    except FileNotFoundError:
        pass
    return {"moved_to": str(dst)}


def _discard_one(name: str, settings: Settings) -> dict:
    """Delete /calls/failed/{name} and its sidecar. Returns the list of paths
    actually removed."""
    name = _safe_name(name)
    failed_dir = settings.calls_dir / FAILED_SUBDIR
    removed: list[str] = []
    for path in (failed_dir / name, failed_dir / f"{name}.error.txt"):
        try:
            path.unlink()
            removed.append(str(path))
        except FileNotFoundError:
            continue
    if not removed:
        raise HTTPException(status_code=404, detail="failed entry not found")
    return {"removed": removed}


@router.get("", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def queue_view(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
):
    pending = list_queue(settings)
    inflight_state = read_inflight_state(settings.log_dir / "watcher.log")
    inflight = [p for p in pending if p["name"] in inflight_state]
    pending = [p for p in pending if p["name"] not in inflight_state]
    failed = list_failed(settings)

    template = "queue/_list.html" if _is_htmx(request) else "queue/index.html"
    return request.app.state.templates.TemplateResponse(
        request, template,
        {
            "user": user,
            "page": "queue",
            "inflight": inflight,
            "pending": pending,
            "failed": failed,
        },
    )


@router.post("/failed/{name}/retry")
@limiter.limit("10/minute")
async def retry_failed(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    ip = _client_ip(request)
    try:
        info = _retry_one(name, settings)
    except HTTPException as exc:
        await audit_record(
            "queue-retry-fail", user=user, ip=ip, target=name, ok=False,
            extra={"err": exc.detail},
        )
        raise
    await audit_record(
        "queue-retry", user=user, ip=ip, target=name, ok=True, extra=info,
    )
    return RedirectResponse(url=f"/queue?did=retry&name={name}", status_code=303)


@router.post("/failed/{name}/discard")
@limiter.limit("10/minute")
async def discard_failed(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    ip = _client_ip(request)
    try:
        info = _discard_one(name, settings)
    except HTTPException as exc:
        await audit_record(
            "queue-discard-fail", user=user, ip=ip, target=name, ok=False,
            extra={"err": exc.detail},
        )
        raise
    await audit_record(
        "queue-discard", user=user, ip=ip, target=name, ok=True, extra=info,
    )
    return RedirectResponse(url=f"/queue?did=discard&name={name}", status_code=303)
