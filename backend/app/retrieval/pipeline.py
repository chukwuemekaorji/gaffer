"""end-to-end retrieval pipeline. this is the function the agent (and
the test endpoint) actually calls.

flow:
  1. rewrite the query into 2-3 variants (haiku)
  2. embed all variants (voyage)
  3. for each variant, run semantic + lexical retrieval in parallel
  4. fuse all per-variant rankings via rrf
  5. rerank the top fused candidates (cohere)
  6. return the final ranked list with metadata for citation
"""

from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy.orm import Session

from app.ingestion.embedder import embed_texts
from app.retrieval.fusion import fuse_candidates
from app.retrieval.lexical import lexical_search
from app.retrieval.query_rewriter import rewrite_query
from app.retrieval.reranker import rerank_candidates
from app.retrieval.schemas import Candidate, RetrievalFilters, RetrievalResult
from app.retrieval.semantic import semantic_search

log = logging.getLogger(__name__)


# per-variant retrieval limits before fusion. larger than the final
# top_n because fusion benefits from having a wider candidate set.
PER_VARIANT_LIMIT = 30
# after fusion, how many candidates we send to the reranker. the reranker
# is the expensive stage so we cap it.
RERANK_INPUT_LIMIT = 20


async def retrieve(
    db: Session,
    *,
    query: str,
    filters: RetrievalFilters | None = None,
    top_n: int = 8,
    use_reranker: bool = True,
) -> RetrievalResult:
    """run the full retrieval pipeline. `use_reranker=False` lets us
    bypass the cohere call when running cheap evals or when a caller
    doesn't have a cohere key."""

    started = time.perf_counter()

    # 1. rewrite
    variants = await rewrite_query(query)

    # 2. embed all variants in one batched call. voyage charges per token,
    # not per call, so batching saves us round-trip latency for free.
    variant_embeddings = await embed_texts(variants, input_type="query")

    # 3. semantic + lexical for each variant, all in parallel. up to
    # 6 small queries (3 variants × 2 retrievers) running concurrently
    # against postgres, all within the connection pool budget.
    tasks: list[asyncio.Task] = []
    for variant, embedding in zip(variants, variant_embeddings):
        tasks.append(
            asyncio.create_task(
                semantic_search(db, query_embedding=embedding, filters=filters, limit=PER_VARIANT_LIMIT)
            )
        )
        tasks.append(
            asyncio.create_task(
                lexical_search(db, query=variant, filters=filters, limit=PER_VARIANT_LIMIT)
            )
        )
    results = await asyncio.gather(*tasks)

    # 4. fuse everything we got
    fused = fuse_candidates(*results, limit=RERANK_INPUT_LIMIT)

    # 5. rerank (optional)
    if use_reranker and fused:
        final = await rerank_candidates(query, fused, top_n=top_n)
    else:
        final = fused[:top_n]

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "retrieve query=%r variants=%d fused=%d final=%d elapsed_ms=%d",
        query, len(variants), len(fused), len(final), elapsed_ms,
    )

    top_score = _best_score(final[0]) if final else None
    return RetrievalResult(
        query=query,
        rewritten_queries=variants,
        candidates=final,
        top_score=top_score,
        n_retrieved=len(final),
    )


def _best_score(candidate: Candidate) -> float:
    """returns the most authoritative score available for this candidate.
    used by the agent later to decide 'is this retrieval confident
    enough to answer, or should we refuse / fall back to web search'."""
    if candidate.rerank_score is not None:
        return candidate.rerank_score
    if candidate.rrf_score is not None:
        return candidate.rrf_score
    if candidate.semantic_score is not None:
        return candidate.semantic_score
    return 0.0