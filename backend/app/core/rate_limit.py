"""A small in-memory rate limit for the routes that cost money or guard
accounts (login, register, password reset, AI and vision calls).

In memory on purpose: the app runs as one Render instance, so there is no
shared state to keep, and no Redis to keep it in. A restart clears the
counters, which only ever makes the limit looser for a moment.

Use as a route dependency:

    @router.post("/login", dependencies=[Depends(rate_limit("login", 10, 60))])
"""
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Tuple

from fastapi import HTTPException, Request, status

from app.core.config import settings

_hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
# Drop idle keys once the table grows past this, so a scan of many IPs
# can't grow it without bound.
_MAX_KEYS = 5000


def client_ip(request: Request) -> str:
    """The caller's address. Render and Vercel put the real client first in
    X-Forwarded-For; without the header (local dev, tests) use the socket."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def reset() -> None:
    """Forget every counter (tests)."""
    _hits.clear()


def _prune(now: float) -> None:
    for key in [k for k, q in _hits.items() if not q or now - q[-1] > 3600]:
        del _hits[key]


def rate_limit(name: str, limit: int, window_seconds: int) -> Callable:
    """Allow `limit` calls per `window_seconds` per client IP for this name."""

    async def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        now = time.monotonic()
        if len(_hits) > _MAX_KEYS:
            _prune(now)
        q = _hits[(name, client_ip(request))]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            retry = max(1, int(window_seconds - (now - q[0])) + 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Try again shortly.",
                headers={"Retry-After": str(retry)},
            )
        q.append(now)

    return dependency
