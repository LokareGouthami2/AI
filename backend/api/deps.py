"""Shared API dependencies: optional token auth and a small rate limiter."""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from backend.config import get_settings
from backend.services.errors import AppError

SESSION_COOKIE = "writeai_session"


def session_value(token: str) -> str:
    """Cookie value proving the password was entered: an HMAC of the token,
    so the password itself is never stored in the browser."""
    return hmac.new(token.encode(), b"writeai-session-v1", hashlib.sha256).hexdigest()


def token_ok(request: Request) -> bool:
    token = get_settings().api_token
    if token is None:
        return True
    secret = token.get_secret_value()
    supplied = request.headers.get("x-api-token") or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if supplied and hmac.compare_digest(supplied, secret):
        return True
    # The web UI logs in once and then uses an HttpOnly cookie, which also
    # covers <img> previews and download links (they can't send headers).
    cookie = request.cookies.get(SESSION_COOKIE, "")
    return bool(cookie) and hmac.compare_digest(cookie, session_value(secret))


def require_token(request: Request) -> None:
    """If WRITEAI_API_TOKEN is set, every /api request must carry it (header
    or login cookie)."""
    if not token_ok(request):
        raise AppError(401, "UNAUTHORIZED", "Please enter the site password.")


class RateLimiter:
    """Sliding-window limiter per (client, bucket). In-process only; a
    multi-instance deployment would move this to Redis."""

    def __init__(self):
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, bucket: str, limit: int, window: float = 60.0) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[(key, bucket)]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                raise AppError(429, "RATE_LIMITED", "Too many requests; please slow down.", {"retry_after_s": int(window - (now - q[0])) + 1})
            q.append(now)


limiter = RateLimiter()


def rate_limit(bucket: str, per_minute: int | None = None):
    def dep(request: Request) -> None:
        s = get_settings()
        if s.env == "test":
            return
        client = request.client.host if request.client else "unknown"
        # Per-route limits are relative to the default of 60/min, so one
        # setting (WRITEAI_RATE_LIMIT_PER_MINUTE) scales them all.
        scale = max(1.0, s.rate_limit_per_minute / 60)
        limiter.check(client, bucket, int((per_minute or s.rate_limit_per_minute) * scale))

    return dep
