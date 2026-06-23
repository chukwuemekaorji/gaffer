"""wraps voyage's embedding api. one place that knows the model name
and dimensions, so when we change embedding models we only touch this
file (and the vector column in the chunks table)."""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

import voyageai

from app.config import get_settings

log = logging.getLogger(__name__)

# voyage-3-large: 1024 dims, top of voyage's general-purpose family.
# alternative considered: voyage-3 (smaller, faster, slightly lower
# recall). went with -large because retrieval quality matters more than
# embedding latency here — we embed once at ingest, query many times.
EMBED_MODEL = "voyage-3-large"
EMBED_DIM = 1024

# voyage accepts up to 128 inputs per call. batching saves real money
# at scale (api round-trip overhead, not per-token cost).
BATCH_SIZE = 64


# voyage distinguishes between embeddings used for indexing documents
# and embeddings used for queries. they're the same model with slightly
# different normalisation — using the right input_type is a measurable
# (~1-2 point) recall boost on standard benchmarks.
InputType = Literal["document", "query"]


_client: voyageai.AsyncClient | None = None


def _get_client() -> voyageai.AsyncClient:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.voyage_api_key:
            raise RuntimeError("VOYAGE_API_KEY is not set in .env")
        _client = voyageai.AsyncClient(api_key=settings.voyage_api_key)
    return _client


async def embed_texts(
    texts: list[str],
    *,
    input_type: InputType = "document",
) -> list[list[float]]:
    """embed a list of strings. handles batching internally so callers
    can pass arbitrary list sizes without thinking about it."""

    if not texts:
        return []

    client = _get_client()
    all_vectors: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        # voyage's async client returns an object with .embeddings,
        # a list[list[float]] matching the input order.
        result = await client.embed(
            texts=batch,
            model=EMBED_MODEL,
            input_type=input_type,
        )
        all_vectors.extend(result.embeddings)
        log.debug("embedded batch %d-%d", i, i + len(batch))

    return all_vectors


async def embed_query(text: str) -> list[float]:
    """convenience wrapper for single-query embedding at retrieval time.
    keeps the input_type='query' detail out of the hot path."""
    vectors = await embed_texts([text], input_type="query")
    return vectors[0]