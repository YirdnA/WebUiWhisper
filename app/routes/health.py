from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..deps import current_user, whisper_client_dep
from ..rate_limit import limiter
from ..whisper_client import WhisperClient, WhisperClientError

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def health_card(
    request: Request,
    user: str = Depends(current_user),
    client: WhisperClient = Depends(whisper_client_dep),
):
    try:
        data = await client.health()
        status = "ok"
    except WhisperClientError as exc:
        data = {"error": str(exc)}
        status = "fail"
    return request.app.state.templates.TemplateResponse(
        request, "partials/health_card.html",
        {"data": data, "status": status},
    )


@router.get("/json", response_class=JSONResponse)
@limiter.limit("60/minute")
async def health_json(
    request: Request,
    user: str = Depends(current_user),
    client: WhisperClient = Depends(whisper_client_dep),
):
    try:
        return JSONResponse(await client.health())
    except WhisperClientError as exc:
        return JSONResponse({"status": "fail", "error": str(exc)}, status_code=502)
