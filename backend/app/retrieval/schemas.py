"""shared data structures used across the retrieval pipeline.
keeping these in one place means each stage (semantic, lexical, rerank)
can stay focused on its own concern without redefining what a 'candidate'
is."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RetrievalFilters:
    """metadata filters applied to retrieval. all fields optional —
    None means no filter on that dimension. these map directly to
    columns on the chunks table."""

    era: str | None = None
    season: str | None = None
    topic: str | None = None
    competition: str | None = None
    players: list[str] | None = None
    # 'fresh_only' = only chunks from the last N days. None = no recency filter.
    max_age_days: int | None = None


@dataclass
class Candidate:
    """one retrieved chunk plus everything we know about its scoring.
    fields fill up as it passes through the pipeline — semantic adds
    semantic_score, lexical adds lexical_score, fusion adds rrf_score,
    rerank adds rerank_score."""

    chunk_id: int
    document_id: int
    content: str
    # metadata copied from the chunks row for citation + filtering
    title: str
    url: str
    source: str
    doc_type: str
    era: str | None
    published_at: datetime | None
    # scores from each stage. None means that stage didn't see it.
    semantic_score: float | None = None
    lexical_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None
    # debug / explainability
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """final output handed back to the agent. candidates are sorted by
    the most authoritative score we computed (rerank if available,
    otherwise rrf, otherwise raw semantic)."""

    query: str
    rewritten_queries: list[str]
    candidates: list[Candidate]
    # the agent uses these to decide whether to answer or refuse
    top_score: float | None
    n_retrieved: int