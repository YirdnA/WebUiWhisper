"""FastAPI dependencies: current user, CSRF, settings, whisper client."""
from __future__ import annotations

import hmac
import secrets
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeSerializer

from .config import Settings, get_settings
from .whisper_client import WhisperClient


def settings_dep() -> Settings:
    return get_settings()


def whisper_client_dep(request: Request) -> WhisperClient:
    client: WhisperClient | None = getattr(request.app.state, "whisper_client", None)
    if client is None:
        raise RuntimeError("WhisperClient not attached to app state")
    return client


def current_user(
    request: Request,
    settings: Annotated[Settings, Depends(settings_dep)],
) -> str:
    if not settings.trust_remote_user:
        raise HTTPException(status_code=501, detail="app-level login not yet enabled")
    user = request.headers.get(settings.remote_user_header)
    if not user:
        if settings.dev_fallback_user:
            return settings.dev_fallback_user
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


# CSRF -----------------------------------------------------------------------
# Double-submit cookie pattern with itsdangerous signing. The token is bound
# to the session id so a token from one user is useless to another.

_CSRF_COOKIE = "ww_csrf"
_CSRF_FIELD = "csrf_token"


def _signer(settings: Settings) -> URLSafeSerializer:
    return URLSafeSerializer(settings.session_secret, salt="ww-csrf")


def issue_csrf(settings: Settings) -> str:
    raw = secrets.token_urlsafe(24)
    return _signer(settings).dumps(raw)


def verify_csrf_token(token: str | None, cookie_value: str | None, settings: Settings) -> bool:
    if not token or not cookie_value:
        return False
    if not hmac.compare_digest(token, cookie_value):
        return False
    try:
        _signer(settings).loads(token)
    except BadSignature:
        return False
    return True


async def require_csrf(
    request: Request,
    ww_csrf: Annotated[str | None, Cookie()] = None,
    settings: Annotated[Settings, Depends(settings_dep)] = None,  # type: ignore[assignment]
) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    form = await request.form()
    token = form.get(_CSRF_FIELD)
    if not verify_csrf_token(token, ww_csrf, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF check failed")


def csrf_cookie_name() -> str:
    return _CSRF_COOKIE


def csrf_field_name() -> str:
    return _CSRF_FIELD
