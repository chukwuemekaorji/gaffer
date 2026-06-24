"""shared types for the agent layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Route(str, Enum):
    """which retrieval strategy the router selected. a single query
    can dispatch to multiple routes in parallel; we represent that as
    a list[Route] on the decision."""

    STATS = "stats"                 # structured football-data lookup
    TACTICAL_RAG = "tactical_rag"   # curated tactical corpus
    RECENT_RAG = "recent_rag"       # news + match reports, recency-weighted
    WEB_SEARCH = "web_search"       # breaking news / last 24h
    REFUSE = "refuse"               # out of scope


@dataclass
class RouterDecision:
    """the router's output. `routes` is what to dispatch; `reasoning` is
    a short justification we log + show in the langfuse trace."""

    routes: list[Route]
    reasoning: str
    # optional structured hints the router extracted from the query.
    # the dispatchers may use them — e.g. filters for the rag retrievers,
    # competition code for the stats tool.
    era: str | None = None
    competition: str | None = None
    players: list[str] = field(default_factory=list)
    needs_recency: bool = False