"""five system configurations for the ablation study.

we compare progressively richer pipelines to show the contribution of
each component. each config is a callable that takes (db, query) and
returns the same shape: list of candidate chunks + final answer +
sources used. the runner doesn't care which config it's calling.

deliberately we do NOT use the actual router for the simpler configs —
they're meant to expose 'what would happen if we only had vector search'.
the full config goes through the full agent loop including the router."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.agent.orchestrator import answer
from app.ingestion.embedder import embed_texts
from app.retrieval.fusion import fuse_candidates
from app.retrieval.lexical import lexical_search
from app.retrieval.query_rewriter import rewrite_query
from app.retrieval.reranker import rerank_candidates
from app.retrieval.schemas import Candidate
from app.retrieval.semantic import semantic_search

log = logging.getLogger(__name__)


@dataclass
class ConfigResult:
    """unified return type so the runner can stay agnostic to which
    config ran. answer + sources may be None for retrieval-only
    configs (1-4); only the full agent config (5) generates text."""
    candidates: list[Candidate]
    answer: str | None = None
    decision_routes: list[str] | None = None
    cited_source_kinds: list[str] | None = None


# --------------------------------------------------------------
# config 1: naive — pure semantic search, no rewriting, no rerank
# --------------------------------------------------------------
async def config_naive(db: Session, query: str, *, k: int = 8) -> ConfigResult:
    embeddings = await embed_texts([query], input_type="query")
    candidates = await semantic_search(db, query_embedding=embeddings[0], limit=k)
    return ConfigResult(candidates=candidates)


# --------------------------------------------------------------
# config 2: + bm25 hybrid (semantic + lexical, fused via rrf)
# --------------------------------------------------------------
async def config_hybrid(db: Session, query: str, *, k: int = 8) -> ConfigResult:
    embeddings = await embed_texts([query], input_type="query")
    semantic, lexical = await asyncio.gather(
        semantic_search(db, query_embedding=embeddings[0], limit=30),
        lexical_search(db, query=query, limit=30),
    )
    fused = fuse_candidates(semantic, lexical, limit=k)
    return ConfigResult(candidates=fused)


# --------------------------------------------------------------
# config 3: + cohere reranker on top of hybrid
# --------------------------------------------------------------
async def config_reranked(db: Session, query: str, *, k: int = 8) -> ConfigResult:
    embeddings = await embed_texts([query], input_type="query")
    semantic, lexical = await asyncio.gather(
        semantic_search(db, query_embedding=embeddings[0], limit=30),
        lexical_search(db, query=query, limit=30),
    )
    fused = fuse_candidates(semantic, lexical, limit=20)
    reranked = await rerank_candidates(query, fused, top_n=k)
    return ConfigResult(candidates=reranked)


# --------------------------------------------------------------
# config 4: + query rewriting on top of hybrid + rerank
# --------------------------------------------------------------
async def config_rewriting(db: Session, query: str, *, k: int = 8) -> ConfigResult:
    variants = await rewrite_query(query)
    variant_embeddings = await embed_texts(variants, input_type="query")

    tasks: list[asyncio.Task] = []
    for variant, emb in zip(variants, variant_embeddings):
        tasks.append(asyncio.create_task(semantic_search(db, query_embedding=emb, limit=30)))
        tasks.append(asyncio.create_task(lexical_search(db, query=variant, limit=30)))
    results = await asyncio.gather(*tasks)

    fused = fuse_candidates(*results, limit=20)
    reranked = await rerank_candidates(query, fused, top_n=k)
    return ConfigResult(candidates=reranked)


# --------------------------------------------------------------
# config 5: full system — router + dispatch + generation
# --------------------------------------------------------------
async def config_full(db: Session, query: str, *, k: int = 8) -> ConfigResult:
    response = await answer(db, query)

    # extract retrieved chunks from the sources (kind='chunk' only)
    chunk_sources = [s for s in response.sources if s.kind == "chunk"]
    cited_kinds = sorted({s.kind for s in response.sources})

    # we don't have the raw candidate list back from the orchestrator,
    # so we synthesise Candidate objects from sources just enough to
    # let recall@k metrics work. metrics that need scoring drop these.
    candidates = [
        Candidate(
            chunk_id=int(s.metadata.get("chunk_id", -1)) if hasattr(s, "metadata") else -1,
            document_id=-1,
            content=s.snippet or "",
            title=s.title,
            url=s.url or "",
            source="",
            doc_type=s.kind,
            era=None,
            published_at=None,
        )
        for s in chunk_sources
    ]
    return ConfigResult(
        candidates=candidates,
        answer=response.answer,
        decision_routes=[r.value for r in response.decision.routes],
        cited_source_kinds=cited_kinds,
    )


# convenient registry the runner iterates over.
CONFIGURATIONS: dict[str, Any] = {
    "1_naive": config_naive,
    "2_hybrid": config_hybrid,
    "3_reranked": config_reranked,
    "4_rewriting": config_rewriting,
    "5_full": config_full,
}