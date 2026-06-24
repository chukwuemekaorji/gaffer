"""runs the router's decision. takes a RouterDecision and dispatches
each selected strategy in parallel, collecting their results into a
single DispatchedEvidence bundle for the context builder.

this is where the 'one query can hit multiple retrieval surfaces'
promise actually happens — asyncio.gather over the chosen branches."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.agent.schemas import Route, RouterDecision
from app.agent.web_search import WebSearchResult, search_web
from app.retrieval.pipeline import retrieve
from app.retrieval.schemas import RetrievalFilters, RetrievalResult
from app.stats import service as stats_service

log = logging.getLogger(__name__)


@dataclass
class StatsEvidence:
    """structured-data evidence bundle. we collect whatever the router
    asked for in one shot rather than make the agent guess what to
    fetch — fewer round-trips."""

    next_fixture: dict[str, Any] | None = None
    recent_results: list[dict[str, Any]] = field(default_factory=list)
    upcoming: list[dict[str, Any]] = field(default_factory=list)
    table_position: dict[str, Any] | None = None
    full_table: list[dict[str, Any]] | None = None


@dataclass
class DispatchedEvidence:
    """everything the dispatchers produced for one query. the context
    builder reads this and serialises it into the prompt for the
    generator."""

    decision: RouterDecision
    tactical: RetrievalResult | None = None
    recent: RetrievalResult | None = None
    stats: StatsEvidence | None = None
    web: WebSearchResult | None = None


# recency window for the recent_rag branch. 30 days catches the last
# few matchdays, transfer rumours of the window, and any news cycle
# we'd want grounded in actually-recent reporting.
RECENT_WINDOW_DAYS = 30


async def _dispatch_tactical(db: Session, query: str, decision: RouterDecision) -> RetrievalResult:
    filters = RetrievalFilters(
        era=decision.era,
        competition=decision.competition,
        players=decision.players or None,
    )
    return await retrieve(db, query=query, filters=filters, top_n=8)


async def _dispatch_recent(db: Session, query: str, decision: RouterDecision) -> RetrievalResult:
    filters = RetrievalFilters(
        competition=decision.competition,
        players=decision.players or None,
        max_age_days=RECENT_WINDOW_DAYS,
    )
    return await retrieve(db, query=query, filters=filters, top_n=8)


async def _dispatch_stats(db: Session, decision: RouterDecision) -> StatsEvidence:
    """we fetch a small bundle of likely-useful stats whenever the
    router picks the stats route. cheap (one or two cached postgres
    reads, maybe one football-data refresh) and gives the generator
    everything it might need to answer table/fixture questions."""
    competition = decision.competition or "premier_league"

    # run in parallel — these are independent reads against the cache.
    next_fix, recent, upcoming, position = await asyncio.gather(
        stats_service.get_next_fixture(db),
        stats_service.get_recent_results(db, limit=5),
        stats_service.get_upcoming_fixtures(db, limit=3),
        stats_service.get_table_position(db, competition=competition),
    )
    return StatsEvidence(
        next_fixture=next_fix,
        recent_results=recent,
        upcoming=upcoming,
        table_position=position,
    )


async def _dispatch_web(query: str) -> WebSearchResult:
    return await search_web(query)


async def dispatch(db: Session, query: str, decision: RouterDecision) -> DispatchedEvidence:
    """runs each branch the router asked for. branches not in the
    decision return None so the context builder knows to skip them."""

    tasks: dict[str, asyncio.Task] = {}

    if Route.TACTICAL_RAG in decision.routes:
        tasks["tactical"] = asyncio.create_task(_dispatch_tactical(db, query, decision))
    if Route.RECENT_RAG in decision.routes:
        tasks["recent"] = asyncio.create_task(_dispatch_recent(db, query, decision))
    if Route.STATS in decision.routes:
        tasks["stats"] = asyncio.create_task(_dispatch_stats(db, decision))
    if Route.WEB_SEARCH in decision.routes:
        tasks["web"] = asyncio.create_task(_dispatch_web(query))

    results: dict[str, Any] = {}
    if tasks:
        completed = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, value in zip(tasks.keys(), completed):
            if isinstance(value, Exception):
                log.warning("dispatch branch=%s failed: %s", key, value)
                results[key] = None
            else:
                results[key] = value

    return DispatchedEvidence(
        decision=decision,
        tactical=results.get("tactical"),
        recent=results.get("recent"),
        stats=results.get("stats"),
        web=results.get("web"),
    )