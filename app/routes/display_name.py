"""Display-name rename: manual ✎ + auto-name from enrichment title.

Storage is the {name}.display_name sidecar (see app/display_name.py).
The canonical {name}.json is never touched. URLs and on-disk filenames
stay stable; only the friendly human-readable name shown in UI and
download Content-Disposition is changed.
"""
from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .. import display_name as display_mod
from .. import enrich as enrich_mod
from .. import enrich_lock
from ..audit import record as audit_record
from ..config import Settings
from ..deps import current_user, require_csrf, settings_dep
from ..fs import find_transcript_path, load_transcript
from ..rate_limit import limiter

router = APIRouter(prefix="/transcripts", tags=["display_name"])

log = logging.getLogger("webuiwhisper.display_name.route")

_NAME_RE = re.compile(r"^(?!\.)(?!.*\.\.)[A-Za-z0-9_.\-, ()]{1,210}$")


def _safe_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"bad transcript name: {name!r}")
    return name


def _ip(request: Request) -> str:
    return request.client.host if request.client else "-"


@router.post("/{name}/display-name")
@limiter.limit("30/minute")
async def set_display_name(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
    display_name: str = Form(default=""),
):
    name = _safe_name(name)
    found = find_transcript_path(name, settings)
    if not found:
        raise HTTPException(status_code=404, detail="transcript not found")
    prev = display_mod.read_display_name(name, settings) or ""
    display_mod.write_display_name(name, display_name, settings)
    new = display_mod.read_display_name(name, settings) or ""
    await audit_record(
        "rename", user=user, ip=_ip(request), target=name, ok=True,
        extra={"from": prev, "to": new},
    )
    import urllib.parse
    return RedirectResponse(
        url=f"/transcripts/{urllib.parse.quote(name, safe='')}?renamed=1",
        status_code=303,
    )


@router.delete("/{name}/display-name")
@limiter.limit("30/minute")
async def clear_display_name_route(
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
    prev = display_mod.read_display_name(name, settings) or ""
    display_mod.clear_display_name(name, settings)
    await audit_record(
        "rename-clear", user=user, ip=_ip(request), target=name, ok=True,
        extra={"from": prev},
    )
    return JSONResponse({"cleared": True})


@router.post("/{name}/display-name/auto")
@limiter.limit("10/minute")
async def auto_name(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    """Propose a display name based on the transcript's `title` pattern.

    If an enrich sidecar already exists with a `title`, use it directly
    (cheap, no LLM call). Otherwise kick off a single-pattern enrich and
    block (up to 60s) waiting for the result. Returns JSON
    `{"title": "..."}` — the UI shows it in the rename input but does NOT
    apply automatically (two-step rename).
    """
    name = _safe_name(name)
    found = find_transcript_path(name, settings)
    if not found:
        raise HTTPException(status_code=404, detail="transcript not found")
    json_path, archived = found

    # Fast path: cached title from a prior full enrich
    sidecar = enrich_mod.read_sidecar(name, settings)
    if sidecar:
        title = (sidecar.get("patterns") or {}).get("title", "")
        if title:
            return JSONResponse({"title": title, "from_cache": True})

    # Slow path: run just the title pattern through the lock
    payload = load_transcript(json_path)

    async def _title_run():
        async with enrich_lock.acquire(name):
            try:
                ollama_url = settings.ollama_base_url
                client = enrich_mod.OllamaClient(ollama_url, settings.enrich_model)
                prompt = enrich_mod._render_prompt(
                    "title", payload, enrich_mod._transcript_text(payload)
                )
                raw = await client.chat(prompt, json_mode=True)
                result = enrich_mod._parse_pattern_response("title", raw)
                return result
            except enrich_mod.OllamaError as exc:
                return ""

    try:
        title = await asyncio.wait_for(_title_run(), timeout=60.0)
    except asyncio.TimeoutError:
        await audit_record(
            "rename-auto-fail", user=user, ip=_ip(request), target=name, ok=False,
            extra={"err": "timeout"},
        )
        raise HTTPException(status_code=504, detail="auto-name timed out")

    if not title:
        return JSONResponse({"title": "", "error": "no title produced"}, status_code=502)

    await audit_record(
        "rename-auto", user=user, ip=_ip(request), target=name, ok=True,
        extra={"title": title},
    )
    return JSONResponse({"title": title, "from_cache": False})
