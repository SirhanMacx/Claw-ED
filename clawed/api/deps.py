"""Shared dependencies for API routes.

Provides: rate limiter, auth guard, database access.
Route modules import from here to avoid circular imports with server.py.
"""
from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict
from functools import wraps
from pathlib import Path

from fastapi import HTTPException, Request

from clawed.database import Database

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

    def limit(self, rate_string: str):
        """Decorator: enforce rate limit like '30/minute' or '5/minute'."""
        count, _, period = rate_string.partition("/")
        max_calls = int(count)
        window = {"second": 1, "minute": 60, "hour": 3600}.get(period, 60)

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
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

                return await func(*args, **kwargs)
            return wrapper
        return decorator


limiter = _RateLimiter()


# ── Auth Token ───────────────────────────────────────────────────────

_TOKEN_FILE = Path(
    os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
) / "api_token"


def _get_or_create_token() -> str:
    """Get existing API token or generate a new one."""
    if _TOKEN_FILE.exists():
        token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        _TOKEN_FILE.chmod(0o600)
    except OSError:
        pass
    return token


def get_api_token() -> str:
    """Public accessor for the API token."""
    return _get_or_create_token()


async def require_auth(request: Request) -> None:
    """FastAPI dependency: require Bearer token on sensitive routes.

    Localhost requests (127.0.0.1) bypass auth when
    EDUAGENT_LOCAL_AUTH_BYPASS=1 is set.
    """
    # Optional localhost bypass (also covers test clients)
    if os.environ.get("EDUAGENT_LOCAL_AUTH_BYPASS") == "1":
        client_ip = request.client.host if request.client else ""
        if client_ip in ("127.0.0.1", "::1", "localhost", "testclient"):
            return

    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = auth[7:]
    if token != _get_or_create_token():
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
