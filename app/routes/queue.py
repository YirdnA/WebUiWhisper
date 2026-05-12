from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..config import Settings
from ..deps import current_user, settings_dep
from ..fs import list_queue
from ..rate_limit import limiter

router = APIRouter(prefix="/queue", tags=["queue"])


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


@router.get("", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def queue_view(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
):
    items = list_queue(settings)
    template = "queue/_list.html" if _is_htmx(request) else "queue/index.html"
    return request.app.state.templates.TemplateResponse(
        request, template,
        {"items": items, "user": user, "page": "queue"},
    )
