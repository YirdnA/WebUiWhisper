"""HTTP routes for transcript enrichment.

- POST /transcripts/{name}/enrich           — kick off a run (CSRF, queues)
- GET  /transcripts/{name}/enrich.json      — sidecar JSON (or 404)
- GET  /transcripts/{name}/enrich.md        — rendered markdown
- DELETE /transcripts/{name}/enrich         — wipe enrich sidecars only

The canonical `{name}.json` is never written by this module.
"""
from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import (
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)

from .. import enrich as enrich_mod
from .. import enrich_lock
from ..audit import record as audit_record
from ..config import Settings
from ..deps import current_user, require_csrf, settings_dep
from ..enrich_md import render_enrich_md
from ..fs import find_transcript_path, load_transcript
from ..rate_limit import limiter

router = APIRouter(prefix="/transcripts", tags=["enrich"])

log = logging.getLogger("webuiwhisper.enrich.route")

_NAME_RE = re.compile(r"^(?!\.)[A-Za-z0-9_.\-]{1,210}$")


def _safe_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"bad transcript name: {name!r}")
    return name


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "-"


def _parse_patterns_csv(s: str, fallback: set[str]) -> set[str]:
    if not s:
        return set(fallback)
    valid = set(enrich_mod.DEFAULT_PATTERN_ORDER) | {enrich_mod.EMBEDDING_KEY}
    out: set[str] = set()
    for tok in s.split(","):
        tok = tok.strip()
        if tok in valid:
            out.add(tok)
    return out or set(fallback)


async def _do_enrich(
    name: str,
    user: str,
    ip: str,
    settings: Settings,
    model: str,
    patterns: set[str],
):
    """Background task: acquire the lock, run the enrichment, write sidecars."""
    async with enrich_lock.acquire(name):
        await audit_record(
            "enrich-start", user=user, ip=ip, target=name, ok=True,
            extra={"model": model, "patterns": sorted(patterns)},
        )
        try:
            found = find_transcript_path(name, settings)
            if not found:
                await audit_record("enrich-fail", user=user, ip=ip, target=name,
                                   ok=False, extra={"err": "transcript not found"})
                return
            json_path, archived = found
            payload = load_transcript(json_path)
            sidecar = await enrich_mod.enrich(
                payload,
                enabled=patterns,
                model=model,
                embed_model=settings.enrich_embed_model,
                settings=settings,
                source_filename=name,
            )
            enrich_mod.write_sidecar(name, sidecar, settings, archived=archived)
            paths = enrich_mod.sidecar_paths(name, settings, archived=archived)
            paths["md"].write_text(
                render_enrich_md(sidecar, with_timecodes=False),
                encoding="utf-8",
            )
            paths["md_timecoded"].write_text(
                render_enrich_md(sidecar, with_timecodes=True),
                encoding="utf-8",
            )
            ok = not sidecar.get("failures")
            await audit_record(
                "enrich-ok" if ok else "enrich-partial",
                user=user, ip=ip, target=name, ok=ok,
                extra={"proc_sec": sidecar.get("proc_sec", 0),
                       "failures": sidecar.get("failures", {})},
            )
        except Exception as exc:
            log.exception("enrich failed for %s", name)
            await audit_record(
                "enrich-fail", user=user, ip=ip, target=name, ok=False,
                extra={"err": str(exc)},
            )


@router.post("/{name}/enrich")
@limiter.limit("10/minute")
async def kick_off(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
    model: str = Form(default=""),
    patterns: str = Form(default=""),
):
    name = _safe_name(name)
    found = find_transcript_path(name, settings)
    if not found:
        raise HTTPException(status_code=404, detail="transcript not found")

    chosen_model = (model.strip() or settings.enrich_model)
    enabled = enrich_mod.load_enabled_patterns(settings)
    chosen_patterns = _parse_patterns_csv(patterns, enabled)

    # Fire-and-forget. The task acquires the global lock; HTMX poll on
    # the detail page reveals progress.
    asyncio.create_task(_do_enrich(
        name=name, user=user, ip=_client_ip(request),
        settings=settings, model=chosen_model, patterns=chosen_patterns,
    ))

    pos = enrich_lock.queue_position(name)
    redirect = f"/transcripts/{urllib.parse.quote(name, safe='')}?enrich=queued"
    if pos is not None and pos > 0:
        redirect += f"&pos={pos}"
    return RedirectResponse(url=redirect, status_code=303)


@router.get("/{name}/enrich.json")
@limiter.limit("60/minute")
async def get_sidecar(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
):
    name = _safe_name(name)
    sidecar = enrich_mod.read_sidecar(name, settings)
    if sidecar is None:
        # 200 with an empty body so HTMX polling can re-fire cheaply
        # without 404 noise in the logs. The poll script treats an
        # empty `{}` as "still running".
        return JSONResponse(content={}, status_code=200)
    return JSONResponse(content=sidecar)


@router.get("/{name}/enrich.md")
@limiter.limit("60/minute")
async def get_md(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    ts: int = Query(default=0, ge=0, le=1),
):
    name = _safe_name(name)
    sidecar = enrich_mod.read_sidecar(name, settings)
    if sidecar is None:
        raise HTTPException(status_code=404, detail="no enrichment yet")
    body = render_enrich_md(sidecar, with_timecodes=bool(ts))
    # Filename uses the display name via the existing helper from transcripts route
    from .transcripts import _content_disposition
    ext = "enrich.timecoded.md" if ts else "enrich.md"
    headers = _content_disposition(name, ext, settings)
    headers["Content-Type"] = "text/markdown; charset=utf-8"
    return Response(content=body, headers=headers, media_type="text/markdown")


@router.delete("/{name}/enrich")
@limiter.limit("10/minute")
async def delete_enrich(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    name = _safe_name(name)
    found = find_transcript_path(name, settings)
    if not found:
        raise HTTPException(status_code=404, detail="transcript not found")
    _, archived = found
    removed = enrich_mod.delete_sidecars(name, settings, archived=archived)
    await audit_record("enrich-delete", user=user, ip=_client_ip(request),
                       target=name, ok=True, extra={"removed": removed})
    return JSONResponse(content={"removed": removed})


@router.get("/{name}/enrich/queue")
async def queue_status(
    name: str,
    user: str = Depends(current_user),
):
    name = _safe_name(name)
    return JSONResponse({"position": enrich_lock.queue_position(name)})
