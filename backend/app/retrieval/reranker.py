"""cohere rerank — second-stage scorer over the fused candidate set.

semantic + lexical + rrf gives us a good ranking, but it's a 'cheap'
ranking — embeddings and bm25 are bag-of-words-ish. the reranker is a
cross-encoder: it sees the query and each candidate together and scores
their relevance directly. expensive per call, so we only run it over
the top ~20 candidates the cheap stages have already shortlisted.

this two-stage retrieve-then-rerank pattern is industry standard for
production rag."""

from __future__ import annotations

import logging

import cohere

from app.config import get_settings
from app.retrieval.schemas import Candidate

log = logging.getLogger(__name__)

RERANK_MODEL = "rerank-english-v3.0"

_client: cohere.AsyncClientV2 | None = None


def _get_client() -> cohere.AsyncClientV2:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.cohere_api_key:
            raise RuntimeError("COHERE_API_KEY is not set in .env")
        _client = cohere.AsyncClientV2(api_key=settings.cohere_api_key)
    return _client


async def rerank_candidates(
    query: str,
    candidates: list[Candidate],
    *,
    top_n: int = 10,
) -> list[Candidate]:
    """reranks candidates by relevance to query, returns top_n. if the
    cohere call fails we fall back to the input ordering — the upstream
    rrf score is already a reasonable ranking."""

    if not candidates:
        return []

    try:
        client = _get_client()
        result = await client.rerank(
            model=RERANK_MODEL,
            query=query,
            documents=[c.content for c in candidates],
            top_n=min(top_n, len(candidates)),
        )

        # cohere returns indices into the input list, plus a relevance score
        reranked: list[Candidate] = []
        for item in result.results:
            c = candidates[item.index]
            c.rerank_score = float(item.relevance_score)
            reranked.append(c)
        log.info("reranked %d candidates, kept top %d", len(candidates), len(reranked))
        return reranked

    except Exception as exc:
        log.warning("reranker failed, falling back to rrf order: %s", exc)
        return candidates[:top_n]