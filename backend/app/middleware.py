"""ip-based rate limiting via upstash redis.

sliding window of fixed length. each request increments a counter
scoped to the client ip; counters expire after the window. this is
the same algorithm cloudflare and stripe use — proven, simple, and
fair under burst.

we use redis instead of in-memory because the deployed backend may
have multiple workers and we want a single shared counter.

deliberately we do NOT rate-limit endpoints other than /chat. health
checks, /retrieve (used by evals), and the stats endpoints aren't
expensive enough to need it."""

from __future__ import annotations

import logging
import time

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.obs.cache import _get_client as get_redis_client

log = logging.getLogger(__name__)


# two windows applied together. the short window absorbs bursts;
# the long window caps overall usage. real-world rate limits are
# almost always a stack of these.
SHORT_WINDOW_SECONDS = 60
SHORT_WINDOW_MAX = 5
LONG_WINDOW_SECONDS = 60 * 60
LONG_WINDOW_MAX = 30


# paths we rate-limit. anything not in this set is unrestricted.
RATE_LIMITED_PREFIXES = ("/chat",)


def _client_ip(request: Request) -> str:
    """resolves the real client ip. behind a proxy (render, vercel)
    we trust the X-Forwarded-For header — its leftmost entry is the
    original client."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not any(path.startswith(p) for p in RATE_LIMITED_PREFIXES):
            return await call_next(request)

        redis = get_redis_client()
        if redis is None:
            # redis unavailable: fail-open. logging would let us know
            # if it persists. we choose open over closed because a
            # rate-limiter outage shouldn't take down the app.
            log.debug("rate limiter: redis unavailable, allowing through")
            return await call_next(request)

        ip = _client_ip(request)
        now = int(time.time())

        # we store one key per window with a TTL equal to the window
        # length. increment, then check. atomic enough for our scale —
        # the small race between INCR and GET only matters at the
        # exact boundary of the limit.
        short_key = f"rl:{ip}:short:{now // SHORT_WINDOW_SECONDS}"
        long_key = f"rl:{ip}:long:{now // LONG_WINDOW_SECONDS}"

        try:
            pipe = redis.pipeline()
            pipe.incr(short_key)
            pipe.expire(short_key, SHORT_WINDOW_SECONDS)
            pipe.incr(long_key)
            pipe.expire(long_key, LONG_WINDOW_SECONDS)
            results = await pipe.execute()
            short_count = int(results[0])
            long_count = int(results[2])
        except Exception as exc:
            log.warning("rate limiter redis error: %s", exc)
            return await call_next(request)

        if short_count > SHORT_WINDOW_MAX:
            return _too_many(
                "rate limit: too many requests in the last minute. wait a bit.",
                retry_after=SHORT_WINDOW_SECONDS - (now % SHORT_WINDOW_SECONDS),
            )
        if long_count > LONG_WINDOW_MAX:
            return _too_many(
                "rate limit: hourly quota reached. come back later.",
                retry_after=LONG_WINDOW_SECONDS - (now % LONG_WINDOW_SECONDS),
            )

        return await call_next(request)


def _too_many(message: str, *, retry_after: int) -> Response:
    return Response(
        content=f'{{"detail": "{message}"}}',
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        media_type="application/json",
        headers={"Retry-After": str(retry_after)},
    )