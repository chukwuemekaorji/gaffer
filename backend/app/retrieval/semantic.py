"""semantic retrieval via pgvector cosine similarity.

we build the sql dynamically because the filter set is variable —
omitting a filter clause entirely is faster than passing NULL and
relying on `where (era = :era or :era is null)`, which defeats the
index. it's a small amount of string-building for a meaningful
planner win."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.retrieval.schemas import Candidate, RetrievalFilters

log = logging.getLogger(__name__)


async def semantic_search(
    db: Session,
    *,
    query_embedding: list[float],
    filters: RetrievalFilters | None = None,
    limit: int = 30,
) -> list[Candidate]:
    """cosine-similarity nearest neighbours for a query embedding,
    with optional metadata filtering. returns up to `limit` candidates
    sorted by similarity (best first)."""

    filters = filters or RetrievalFilters()
    where_clauses: list[str] = []
    params: dict[str, object] = {
        "embedding": str(query_embedding),
        "limit": limit,
    }

    if filters.era:
        where_clauses.append("c.era = :era")
        params["era"] = filters.era
    if filters.season:
        where_clauses.append("c.season = :season")
        params["season"] = filters.season
    if filters.topic:
        where_clauses.append("c.topic = :topic")
        params["topic"] = filters.topic
    if filters.competition:
        where_clauses.append("c.competition = :competition")
        params["competition"] = filters.competition
    if filters.players:
        # `&&` is the array-overlap operator: true if any element matches.
        # gin index on players_mentioned makes this fast.
        where_clauses.append("c.players_mentioned && :players")
        params["players"] = filters.players
    if filters.max_age_days is not None:
        where_clauses.append(
            "c.published_at > now() - make_interval(days => :max_age_days)"
        )
        params["max_age_days"] = filters.max_age_days

    where_sql = ("where " + " and ".join(where_clauses)) if where_clauses else ""

    # cosine distance is `<=>` in pgvector; we convert to similarity
    # (1 - distance) for an intuitive 0..1 score where higher = better.
    sql = f"""
        select
            c.id              as chunk_id,
            c.document_id     as document_id,
            c.content         as content,
            d.title           as title,
            d.url             as url,
            d.source          as source,
            d.doc_type        as doc_type,
            c.era             as era,
            c.published_at    as published_at,
            1 - (c.embedding <=> cast(:embedding as vector)) as similarity
        from chunks c
        join documents d on d.id = c.document_id
        {where_sql}
        order by c.embedding <=> cast(:embedding as vector)
        limit :limit
    """

    rows = db.execute(text(sql), params).mappings().all()

    candidates = [
        Candidate(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            content=row["content"],
            title=row["title"],
            url=row["url"],
            source=row["source"],
            doc_type=row["doc_type"],
            era=row["era"],
            published_at=row["published_at"],
            semantic_score=float(row["similarity"]),
        )
        for row in rows
    ]
    log.info("semantic search returned %d candidates", len(candidates))
    return candidates