"""thin api wrapper around the retrieval pipeline. exists primarily
so we can hit it with curl / a frontend and watch the retrieval
behaviour without a full agent loop on top."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.retrieval.pipeline import retrieve
from app.retrieval.schemas import RetrievalFilters

router = APIRouter(prefix="/retrieve", tags=["retrieval"])


class RetrieveRequest(BaseModel):
    query: str
    top_n: int = Field(default=8, ge=1, le=20)
    era: str | None = None
    season: str | None = None
    topic: str | None = None
    competition: str | None = None
    players: list[str] | None = None
    max_age_days: int | None = None
    use_reranker: bool = True


class CandidatePayload(BaseModel):
    chunk_id: int
    document_id: int
    content: str
    title: str
    url: str
    source: str
    doc_type: str
    era: str | None
    semantic_score: float | None
    lexical_score: float | None
    rrf_score: float | None
    rerank_score: float | None


class RetrieveResponse(BaseModel):
    query: str
    rewritten_queries: list[str]
    candidates: list[CandidatePayload]
    top_score: float | None
    n_retrieved: int


@router.post("", response_model=RetrieveResponse)
async def retrieve_endpoint(
    req: RetrieveRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    filters = RetrievalFilters(
        era=req.era,
        season=req.season,
        topic=req.topic,
        competition=req.competition,
        players=req.players,
        max_age_days=req.max_age_days,
    )
    result = await retrieve(
        db,
        query=req.query,
        filters=filters,
        top_n=req.top_n,
        use_reranker=req.use_reranker,
    )
    return {
        "query": result.query,
        "rewritten_queries": result.rewritten_queries,
        "candidates": [
            {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "content": c.content,
                "title": c.title,
                "url": c.url,
                "source": c.source,
                "doc_type": c.doc_type,
                "era": c.era,
                "semantic_score": c.semantic_score,
                "lexical_score": c.lexical_score,
                "rrf_score": c.rrf_score,
                "rerank_score": c.rerank_score,
            }
            for c in result.candidates
        ],
        "top_score": result.top_score,
        "n_retrieved": result.n_retrieved,
    }