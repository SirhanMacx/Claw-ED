"""Shared dependencies for API routes.

Provides: rate limiter, auth guard, database access.
Route modules import from here to avoid circular imports with server.py.
"""
from __future__ import annotations

import contextlib
import logging
import os
import secrets
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from fastapi import HTTPException, Request

from clawed.database import Database
from clawed.paths import api_token_path

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])

logger = logging.getLogger(__name__)

# ── Rate Limiter (in-memory, per-process) ────────────────────────────

_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_request_count: int = 0


def _cleanup_rate_store(window: int) -> None:
    """Remove stale entries from the rate store to prevent memory leaks.

    Called every 100th request. Removes timestamps older than the window
    and deletes keys that have become empty.
    """
    now = time.time()
    empty_keys = []
    for key in list(_rate_store.keys()):
        _rate_store[key] = [t for t in _rate_store[key] if t > now - window]
        if not _rate_store[key]:
            empty_keys.append(key)
    for key in empty_keys:
        del _rate_store[key]


class _RateLimiter:
    """Simple in-memory rate limiter. No external dependencies."""

    def limit(self, rate_string: str) -> Callable[[F], F]:
        """Decorator: enforce rate limit like '30/minute' or '5/minute'."""
        count, _, period = rate_string.partition("/")
        max_calls = int(count)
        window = {"second": 1, "minute": 60, "hour": 3600}.get(period, 60)

        def decorator(func: F) -> F:
            @wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                global _rate_request_count

                # Extract request from args or kwargs
                request = kwargs.get("request")
                if request is None:
                    for arg in args:
                        if isinstance(arg, Request):
                            request = arg
                            break

                if request is not None:
                    client = request.client.host if request.client else "unknown"
                    key = f"{client}:{func.__name__}"
                    now = time.time()

                    # Periodic full cleanup to prevent memory leak
                    _rate_request_count += 1
                    if _rate_request_count % 100 == 0:
                        _cleanup_rate_store(window)

                    # Prune old timestamps for this key
                    _rate_store[key] = [
                        t for t in _rate_store[key] if t > now - window
                    ]

                    if len(_rate_store[key]) >= max_calls:
                        raise HTTPException(
                            status_code=429,
                            detail=f"Rate limit exceeded ({rate_string})",
                        )
                    _rate_store[key].append(now)
                else:
                    # v4.11.2026.1 security fix (P2-7): the old limiter
                    # would silently no-op when the handler signature
                    # didn't include a `Request` parameter, so forgetting
                    # to add it disabled the rate limit with zero signal.
                    # Now we log a warning every time a decorated handler
                    # runs without a Request — noisy enough to catch in
                    # dev but non-fatal so production traffic isn't
                    # broken by a missing annotation.
                    logger.warning(
                        "Rate limiter on %s has no Request in signature; "
                        "limit %s is NOT being enforced. Add "
                        "`request: Request` to the handler.",
                        func.__name__,
                        rate_string,
                    )

                return await func(*args, **kwargs)
            # wrapper preserves func's signature at runtime via @wraps
            return wrapper  # type: ignore[return-value]
        return decorator


limiter = _RateLimiter()


# ── Auth Token ───────────────────────────────────────────────────────

def _get_or_create_token() -> str:
    """Get existing API token or generate a new one."""
    token_file = api_token_path()
    if token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token, encoding="utf-8")
    with contextlib.suppress(OSError):
        token_file.chmod(0o600)
    return token


def get_api_token() -> str:
    """Public accessor for the API token."""
    return _get_or_create_token()


def _via_cloudflare_edge(request: Request) -> bool:
    """True if the request arrived through Cloudflare (i.e. the public tunnel).

    Cloudflare stamps every request it proxies with a ``Cf-Ray`` header. Genuine
    loopback traffic — the teacher's own browser or the menu-bar app hitting
    127.0.0.1 directly — never has it. The agent binds loopback only, so the ONLY
    way a request reaches it from off-machine is the named tunnel, which always
    carries ``Cf-Ray``; an off-machine caller cannot strip it (Cloudflare adds it
    at the edge, *after* they connect). So "no Cf-Ray" reliably means the request
    is genuinely local.
    """
    return bool(request.headers.get("cf-ray"))


def local_bypass_ok(request: Request) -> bool:
    """Whether the loopback auth bypass applies to this request.

    True only when ``EDUAGENT_LOCAL_AUTH_BYPASS=1`` AND the request is genuinely
    local: a loopback client that did NOT come through Cloudflare. This is what
    stops the public tunnel from being an open door — tunnel traffic always
    carries a ``Cf-Ray`` header, so it never bypasses and must present a token,
    while the teacher's own on-Mac browser/menu-bar access stays password-free.
    """
    if os.environ.get("EDUAGENT_LOCAL_AUTH_BYPASS") != "1":
        return False
    if _via_cloudflare_edge(request):
        return False  # came over the public tunnel — never bypass
    client_ip = request.client.host if request.client else ""
    return client_ip in ("127.0.0.1", "::1", "localhost", "testclient")


async def require_auth(request: Request) -> None:
    """FastAPI dependency: require Bearer token on sensitive routes.

    Genuinely-local requests bypass auth when EDUAGENT_LOCAL_AUTH_BYPASS=1, but
    requests proxied through the public Cloudflare tunnel never do (see
    local_bypass_ok) — so the tunnel always requires a token.

    v4.11.2026: uses secrets.compare_digest for timing-safe comparison.
    """
    if local_bypass_ok(request):
        return

    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = auth[7:]
    expected = _get_or_create_token()
    # Timing-safe: compare_digest avoids leaking the first-diverging byte
    # via wall-clock differences on mismatch. Both operands must be str
    # (bytes also work) and must be the same type.
    if not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid auth token")


# ── Database ─────────────────────────────────────────────────────────

_db: Database | None = None


def get_db() -> Database:
    """Get or create the shared Database instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db


def set_db(db: Database | None) -> None:
    """Set the shared Database instance (used by lifespan handler)."""
    global _db
    _db = db
