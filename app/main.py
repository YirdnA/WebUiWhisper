"""FastAPI app factory for WebUiWhisper."""
from __future__ import annotations

import contextlib
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .db import init_db
from .deps import csrf_cookie_name, csrf_field_name, issue_csrf
from .rate_limit import limiter
from .routes import archive as archive_route
from .routes import audio as audio_route
from .routes import enrich as enrich_route
from .routes import settings_enrich as settings_enrich_route
from .routes import audit as audit_route
from .routes import bulk as bulk_route
from .routes import disk as disk_route
from .routes import edit as edit_route
from .routes import health as health_route
from .routes import logs as logs_route
from .routes import policy as policy_route
from .routes import progress as progress_route
from .routes import queue as queue_route
from .routes import rediarize as rediarize_route
from .routes import transcripts as transcripts_route
from .routes import uploads as uploads_route
from .whisper_client import WhisperClient


# --- logging -----------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("webuiwhisper.main")


# --- security headers --------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Mirror the headers Apache sets, so direct-localhost access is also safe."""

    HEADERS = {
        "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        ),
    }

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for k, v in self.HEADERS.items():
            response.headers.setdefault(k, v)
        return response


# --- app factory -------------------------------------------------------------


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db(settings)
    app.state.whisper_client = WhisperClient(settings)
    log.info("WebUiWhisper started — upstream %s", settings.whisper_api_url)
    try:
        yield
    finally:
        await app.state.whisper_client.aclose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="WebUiWhisper",
        version="0.1.0",
        docs_url=None,        # disable interactive docs in prod
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    app.add_middleware(SecurityHeadersMiddleware)

    # Templates / static
    here = Path(__file__).parent
    app.state.templates = Jinja2Templates(directory=str(here / "templates"))
    app.state.templates.env.globals["csrf_field_name"] = csrf_field_name
    app.state.templates.env.filters["fmt_ts"] = _fmt_ts
    app.state.templates.env.filters["pretty_name"] = _pretty_name
    app.state.templates.env.filters["stem"] = _stem
    app.state.templates.env.filters["rel_ts"] = _rel_ts
    app.state.templates.env.filters["display_name"] = _display_name_filter
    app.state.templates.env.filters["transcript_hashtags"] = _hashtags_filter
    app.mount("/static", StaticFiles(directory=str(here / "static")), name="static")

    # Routes
    app.include_router(transcripts_route.router)
    app.include_router(uploads_route.router)
    app.include_router(queue_route.router)
    app.include_router(health_route.router)
    app.include_router(audit_route.router)
    app.include_router(audio_route.router)
    app.include_router(progress_route.router)
    app.include_router(rediarize_route.router)
    app.include_router(edit_route.router)
    app.include_router(bulk_route.router)
    app.include_router(logs_route.router)
    app.include_router(disk_route.router)
    app.include_router(policy_route.router)
    app.include_router(archive_route.router)
    app.include_router(enrich_route.router)
    app.include_router(settings_enrich_route.router)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return _redirect(request, "/transcripts")

    @app.middleware("http")
    async def ensure_csrf_cookie(request: Request, call_next):
        # Resolve settings fresh per request rather than closure-capturing
        # the create_app()-time value. get_settings() is lru_cached so the
        # overhead is a function call; this lets tests rebind settings
        # after module import without the middleware getting a stale view.
        live_settings = get_settings()
        existing = request.cookies.get(csrf_cookie_name())
        if existing:
            request.state.csrf_token = existing
            new_token = None
        else:
            new_token = issue_csrf(live_settings)
            request.state.csrf_token = new_token
        response = await call_next(request)
        if new_token is not None:
            response.set_cookie(
                csrf_cookie_name(), new_token,
                httponly=True, secure=True, samesite="strict", path="/",
                max_age=60 * 60 * 8,
            )
        return response

    return app


def _redirect(request: Request, target: str):
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=target, status_code=303)


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})


def _fmt_ts(value) -> str:
    """Unix epoch -> "YYYY-MM-DD HH:MM:SS" UTC. Pass-through on bad input."""
    import datetime as _dt
    try:
        return _dt.datetime.fromtimestamp(float(value), tz=_dt.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except (TypeError, ValueError):
        return str(value)


_PRETTY_NAME_RE = __import__("re").compile(
    r"^(?P<stem>.+?)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2}-\d{2})"
    r"(?P<ext>\.[A-Za-z0-9]+)?$"
)


def _pretty_name(value) -> str:
    """Friendly title for transcripts named like `nanotalks_2026-05-12_19-40-56.flac`.

    Output: `nanotalks (2026-05-12 19:40:56)`. The original is returned
    unchanged if the pattern doesn't match (older / hand-named files)."""
    s = str(value)
    m = _PRETTY_NAME_RE.match(s)
    if not m:
        return s
    stem = m.group("stem")
    date = m.group("date")
    t = m.group("time").replace("-", ":")
    return f"{stem} ({date} {t})"


def _stem(value) -> str:
    """Just the room/recording name without the timestamp suffix and extension.
    `nanotalks_2026-05-12_19-40-56.flac` -> `nanotalks`. Falls back to the
    filename stem (no extension) if the timestamp pattern doesn't match."""
    s = str(value)
    m = _PRETTY_NAME_RE.match(s)
    if m:
        return m.group("stem")
    # No timestamp suffix — strip just the extension.
    dot = s.rfind(".")
    return s[:dot] if dot > 0 else s


def _rel_ts(value) -> str:
    """Unix epoch -> short relative string ("5 s ago", "12 min ago",
    "3 h ago", "yesterday", "YYYY-MM-DD"). Falls back to str(value) on bad input."""
    import datetime as _dt
    try:
        t = float(value)
    except (TypeError, ValueError):
        return str(value)
    now = _dt.datetime.now(tz=_dt.timezone.utc).timestamp()
    delta = now - t
    if delta < 0:
        # Clock skew or future timestamp; show absolute date.
        try:
            return _dt.datetime.fromtimestamp(t, tz=_dt.timezone.utc).strftime("%Y-%m-%d")
        except (OSError, OverflowError, ValueError):
            return str(value)
    if delta < 60:
        return f"{int(delta)} s ago"
    if delta < 3600:
        return f"{int(delta // 60)} min ago"
    if delta < 86400:
        return f"{int(delta // 3600)} h ago"
    if delta < 86400 * 2:
        return "yesterday"
    if delta < 86400 * 7:
        return f"{int(delta // 86400)} d ago"
    try:
        return _dt.datetime.fromtimestamp(t, tz=_dt.timezone.utc).strftime("%Y-%m-%d")
    except (OSError, OverflowError, ValueError):
        return str(value)


def _hashtags_filter(value) -> list[str]:
    """List of hashtags for a transcript, or [] if no enrichment sidecar."""
    from .fs import transcript_hashtags
    return transcript_hashtags(str(value), get_settings())


def _display_name_filter(value) -> str:
    """Resolve a transcript's friendly name: explicit display_name sidecar
    if set, otherwise pretty_name(value) (timestamp suffix → human form).
    Imported locally to keep the dep on app.display_name out of the module
    import graph cycle."""
    from .display_name import read_display_name
    name = str(value)
    explicit = read_display_name(name, get_settings())
    if explicit:
        return explicit
    return _pretty_name(name)


app = create_app()
