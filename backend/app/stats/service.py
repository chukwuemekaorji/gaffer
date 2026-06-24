"""the agent-facing api over structured stats.

every function here is a candidate 'tool' the router can dispatch to.
they all follow the same pattern: read from postgres cache first; refresh
from football-data.org if the cache is stale; return shaped data ready
for citation."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.stats import repository
from app.stats.client import FootballDataClient
from app.stats.constants import COMPETITION_CODES, CURRENT_SEASON

log = logging.getLogger(__name__)


async def _refresh_fixtures(db: Session) -> int:
    """pulls all united's fixtures for the current season and upserts.
    one api call to football-data, then the cache is good for ~30 min."""
    client = FootballDataClient()
    matches = await client.get_team_fixtures()
    n = repository.upsert_fixtures(db, matches)
    log.info("refreshed fixtures cache count=%d", n)
    return n


async def _refresh_league_table(db: Session, competition_code: str) -> int:
    client = FootballDataClient()
    standings = await client.get_competition_standings(competition_code)
    n = repository.upsert_league_table(
        db,
        competition_code=competition_code.lower(),
        season=CURRENT_SEASON,
        standings_payload=standings,
    )
    log.info("refreshed table cache competition=%s rows=%d", competition_code, n)
    return n


async def ensure_fresh_fixtures(db: Session) -> None:
    age = repository.fixtures_age(db)
    if age is None or age > repository.FIXTURE_STALENESS:
        try:
            await _refresh_fixtures(db)
        except Exception as exc:
            # cache may still be useful even if upstream is down.
            log.warning("fixture refresh failed, returning cached data: %s", exc)


async def ensure_fresh_table(db: Session, competition_code: str) -> None:
    age = repository.league_table_age(
        db, competition=competition_code.lower(), season=CURRENT_SEASON
    )
    if age is None or age > repository.TABLE_STALENESS:
        try:
            await _refresh_league_table(db, competition_code)
        except Exception as exc:
            log.warning("table refresh failed, returning cached data: %s", exc)


# ============================================================
# the tool surface — every function here is something the agent
# can call as a tool. return shapes are plain dicts so they
# serialise cleanly into prompts.
# ============================================================


async def get_next_fixture(db: Session) -> dict[str, Any] | None:
    await ensure_fresh_fixtures(db)
    return repository.get_next_fixture(db)


async def get_recent_results(db: Session, *, limit: int = 5) -> list[dict[str, Any]]:
    await ensure_fresh_fixtures(db)
    return repository.get_recent_results(db, limit=limit)


async def get_upcoming_fixtures(db: Session, *, limit: int = 5) -> list[dict[str, Any]]:
    await ensure_fresh_fixtures(db)
    return repository.get_upcoming_fixtures(db, limit=limit)


async def get_table_position(
    db: Session, *, competition: str = "premier_league"
) -> dict[str, Any] | None:
    """united's row in the given competition. defaults to premier league
    because that's the most-asked-about competition by far."""
    code = COMPETITION_CODES.get(competition)
    if not code:
        return None
    await ensure_fresh_table(db, code)
    return repository.get_team_table_row(
        db, competition=code, season=CURRENT_SEASON
    )


async def get_full_table(
    db: Session, *, competition: str = "premier_league"
) -> list[dict[str, Any]]:
    code = COMPETITION_CODES.get(competition)
    if not code:
        return []
    await ensure_fresh_table(db, code)
    return repository.get_full_table(db, competition=code, season=CURRENT_SEASON)