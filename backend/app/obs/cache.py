"""semantic cache: redis-backed cache keyed by query embedding similarity.

how it works:
  1. for an incoming query, embed it
  2. compare against every cached query's embedding (cosine similarity)
  3. if any hit clears the similarity threshold, return its cached answer
  4. otherwise let the agent run normally, then store the result

we use redis because:
  - the upstash free tier is plenty for this volume
  - it gives us TTL out of the box (24h here — stale enough that stats
    won't get served from cache forever)
  - it's a separate store from postgres, so the agent path doesn't
    contend with ingestion

the similarity threshold (0.95) is conservative. lower (0.9) means more
cache hits but risks serving the wrong answer; higher (0.98) means
near-duplicates only, fewer hits. tuneable based on eval data later."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import redis.asyncio as redis

from app.config import get_settings
from app.ingestion.embedder import embed_texts

log = logging.getLogger(__name__)

# tuning knobs
SIMILARITY_THRESHOLD = 0.95
CACHE_TTL_SECONDS = 60 * 60 * 24       # 24 hours
KEY_PREFIX = "gaffer:cache:"
INDEX_KEY = "gaffer:cache:index"        # sorted set of all cache keys


@dataclass
class CachedResponse:
    query: str
    answer: str
    sources_json: str                   # serialised list of source dicts
    decision_json: str                  # serialised router decision
    latency_ms: int                     # latency of the *original* run
    age_seconds: int                    # how long this entry has been cached


_client: redis.Redis | None = None


def _get_client() -> redis.Redis | None:
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    if not settings.redis_url:
        log.debug("redis not configured, cache disabled")
        return None

    try:
        _client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )
        return _client
    except Exception as exc:
        log.warning("redis init failed: %s", exc)
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))


async def lookup(query: str) -> CachedResponse | None:
    """semantic cache lookup. returns the cached response if any
    previously-cached query's embedding is within the threshold;
    otherwise None.

    the linear scan over cached embeddings is fine at our scale
    (a few hundred to a few thousand entries). when we grow past that
    we'd switch to a vector index — redis stack supports it natively,
    upstash doesn't yet. for now the scan is O(n) and bounded by ttl."""
    client = _get_client()
    if client is None:
        return None

    try:
        query_embedding = await embed_texts([query], input_type="query")
        query_vec = query_embedding[0]

        # the index is a redis set of all keys with active entries
        keys = await client.smembers(INDEX_KEY)
        if not keys:
            return None

        best: tuple[float, dict[str, Any]] | None = None
        for key in keys:
            raw = await client.get(key)
            if raw is None:
                # entry expired — drop it from the index lazily
                await client.srem(INDEX_KEY, key)
                continue
            entry = json.loads(raw)
            sim = _cosine(query_vec, entry["embedding"])
            if sim >= SIMILARITY_THRESHOLD and (best is None or sim > best[0]):
                best = (sim, entry)

        if best is None:
            return None

        sim, entry = best
        log.info("cache hit query=%r similarity=%.3f", query, sim)

        # compute age from stored timestamp
        import time
        age = int(time.time() - entry["stored_at"])

        return CachedResponse(
            query=entry["query"],
            answer=entry["answer"],
            sources_json=entry["sources_json"],
            decision_json=entry["decision_json"],
            latency_ms=entry["latency_ms"],
            age_seconds=age,
        )

    except Exception as exc:
        log.warning("cache lookup failed: %s", exc)
        return None


async def store(
    *,
    query: str,
    answer: str,
    sources_json: str,
    decision_json: str,
    latency_ms: int,
) -> None:
    """saves a successful agent response to the cache. fire-and-forget;
    failures here never propagate to the user."""
    client = _get_client()
    if client is None:
        return

    try:
        import time
        query_embedding = await embed_texts([query], input_type="query")

        # use a hash of the query as the key. simple and avoids special
        # characters in redis keys.
        import hashlib
        key = KEY_PREFIX + hashlib.sha256(query.encode()).hexdigest()[:16]

        entry = {
            "query": query,
            "embedding": query_embedding[0],
            "answer": answer,
            "sources_json": sources_json,
            "decision_json": decision_json,
            "latency_ms": latency_ms,
            "stored_at": int(time.time()),
        }

        await client.set(key, json.dumps(entry), ex=CACHE_TTL_SECONDS)
        await client.sadd(INDEX_KEY, key)
        log.info("cache stored query=%r key=%s", query, key)

    except Exception as exc:
        log.warning("cache store failed: %s", exc)