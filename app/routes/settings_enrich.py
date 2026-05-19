"""Settings UI for enrich pattern toggles (per-pattern enable/disable)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import enrich as enrich_mod
from ..audit import record as audit_record
from ..config import Settings
from ..deps import current_user, require_csrf, settings_dep
from ..rate_limit import limiter

router = APIRouter(prefix="/settings/enrich", tags=["settings"])

log = logging.getLogger("webuiwhisper.settings.enrich")


def _templates(request: Request):
    return request.app.state.templates


@router.get("", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def view(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
):
    enabled = enrich_mod.load_enabled_patterns(settings)
    rows = [
        {"key": k,
         "enabled": k in enabled,
         "description": enrich_mod.PROMPTS.get(k, {}).get("description", "")}
        for k in enrich_mod.DEFAULT_PATTERN_ORDER
    ]
    # Embedding has no prompt file — describe it inline.
    rows.append({
        "key": enrich_mod.EMBEDDING_KEY,
        "enabled": enrich_mod.EMBEDDING_KEY in enabled,
        "description": "Vector via nomic-embed-text (enables future semantic search).",
    })
    return _templates(request).TemplateResponse(
        request, "settings/enrich.html",
        {
            "user": user,
            "page": "settings",
            "rows": rows,
            "default_model": settings.enrich_model,
        },
    )


@router.post("")
@limiter.limit("10/minute")
async def save(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    form = await request.form()
    # A checkbox absent from the POST body is "unchecked".
    valid = set(enrich_mod.DEFAULT_PATTERN_ORDER) | {enrich_mod.EMBEDDING_KEY}
    new_set: set[str] = set()
    for key in valid:
        if form.get(f"pat_{key}") == "on":
            new_set.add(key)
    prev = enrich_mod.load_enabled_patterns(settings)
    enrich_mod.save_enabled_patterns(new_set, settings)
    added = sorted(new_set - prev)
    removed = sorted(prev - new_set)
    await audit_record(
        "settings-enrich", user=user,
        ip=request.client.host if request.client else "-",
        target="enrich-settings", ok=True,
        extra={"added": added, "removed": removed},
    )
    return RedirectResponse(url="/settings/enrich?saved=1", status_code=303)
