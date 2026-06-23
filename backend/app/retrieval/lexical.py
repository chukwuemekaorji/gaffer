"""lexical retrieval — postgres full-text search for candidate generation,
then BM25 scoring on python side.

why two stages? postgres tsvector + websearch_to_tsquery is great for
'find documents containing these terms' but its built-in ts_rank scoring
isn't bm25-shaped. running bm25 on a small candidate set in python gives
us the standard, well-understood scoring without forking out to elastic.

bm25 cares about term frequency, inverse document frequency, and document
length normalisation — all things ts_rank approximates but doesn't quite
match."""

from __future__ import annotations

import logging
import re

from rank_bm25 import BM25Okapi
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.retrieval.schemas import Candidate, RetrievalFilters

log = logging.getLogger(__name__)

# how many candidates we ask postgres for. we'll then bm25-rank these
# and return the top-k. needs to be larger than the final limit to give
# bm25 something meaningful to discriminate between.
CANDIDATE_POOL_SIZE = 100

# very simple tokeniser. lowercase, split on non-letters. bm25's quality
# is robust to tokeniser choice — fancier wordpiece-style tokenisation
# barely moves the needle on prose retrieval.
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text_: str) -> list[str]:
    return _TOKEN_RE.findall(text_.lower())


def _build_tsquery(query: str) -> str:
    """builds a websearch_to_tsquery-compatible string. handles common
    cases (multi-word queries, quoted phrases) by just passing them
    through — websearch_to_tsquery parses google-style syntax natively."""
    return query.strip() or "manchester united"      # empty queries get a safe default


async def lexical_search(
    db: Session,
    *,
    query: str,
    filters: RetrievalFilters | None = None,
    limit: int = 30,
) -> list[Candidate]:
    """returns top `limit` candidates by bm25 score over postgres
    full-text candidate set, with the same filter semantics as
    semantic_search."""

    filters = filters or RetrievalFilters()
    where_clauses: list[str] = []
    params: dict[str, object] = {
        "tsquery": _build_tsquery(query),
        "pool_size": CANDIDATE_POOL_SIZE,
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
        where_clauses.append("c.players_mentioned && :players")
        params["players"] = filters.players
    if filters.max_age_days is not None:
        where_clauses.append(
            "c.published_at > now() - make_interval(days => :max_age_days)"
        )
        params["max_age_days"] = filters.max_age_days

    fts_clause = "to_tsvector('english', c.content) @@ websearch_to_tsquery('english', :tsquery)"
    where_clauses.append(fts_clause)
    where_sql = "where " + " and ".join(where_clauses)

    # candidate fetch — we use ts_rank to roughly pre-order the pool so
    # the top of the pool is likely-relevant. bm25 will do the precise
    # ranking on this set.
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
            ts_rank(to_tsvector('english', c.content),
                    websearch_to_tsquery('english', :tsquery)) as ts_rank
        from chunks c
        join documents d on d.id = c.document_id
        {where_sql}
        order by ts_rank desc
        limit :pool_size
    """

    rows = db.execute(text(sql), params).mappings().all()
    if not rows:
        return []

    # bm25 scoring over the candidate pool
    corpus_tokens = [_tokenize(row["content"]) for row in rows]
    if not any(corpus_tokens):
        return []

    bm25 = BM25Okapi(corpus_tokens)
    query_tokens = _tokenize(query)
    scores = bm25.get_scores(query_tokens)

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
            lexical_score=float(score),
        )
        for row, score in zip(rows, scores)
    ]
    candidates.sort(key=lambda c: c.lexical_score or 0.0, reverse=True)
    candidates = candidates[:limit]
    log.info("lexical search returned %d candidates", len(candidates))
    return candidates