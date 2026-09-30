"""Shared API dependencies: optional token auth and a small rate limiter."""

from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from backend.config import get_settings
from backend.services.errors import AppError


def require_token(request: Request) -> None:
    """If WRITEAI_API_TOKEN is set, every /api request must carry it."""
    token = get_settings().api_token
    if token is None:
        return
    supplied = request.headers.get("x-api-token") or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not supplied or not hmac.compare_digest(supplied, token.get_secret_value()):
        raise AppError(401, "UNAUTHORIZED", "A valid API token is required.")


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
        limiter.check(client, bucket, per_minute or s.rate_limit_per_minute)

    return dep
