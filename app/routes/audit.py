from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from ..audit import recent as recent_audit
from ..config import Settings
from ..deps import current_user, settings_dep
from ..rate_limit import limiter

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def audit_view(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0, le=100_000),
):
    rows = await recent_audit(limit=limit, offset=offset, settings=settings)
    return request.app.state.templates.TemplateResponse(
        request, "audit/index.html",
        {"rows": rows, "user": user, "page": "audit",
         "limit": limit, "offset": offset},
    )
