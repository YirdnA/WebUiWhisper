"""slowapi limiter and key function."""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _client_key(request: Request) -> str:
    # Trust X-Forwarded-For only when --proxy-headers is on (uvicorn flag).
    # slowapi's default reads request.client.host which uvicorn populates from
    # the Forwarded-* headers when forwarded-allow-ips includes the proxy.
    return get_remote_address(request)


limiter = Limiter(key_func=_client_key, headers_enabled=True)
