"""thin async client over football-data.org's rest api.

we don't use any third-party sdk because football-data's api is small
and well-shaped — direct httpx calls are easier to debug and don't
introduce another dependency to keep current."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.stats.constants import MANCHESTER_UNITED_TEAM_ID

log = logging.getLogger(__name__)

BASE_URL = "https://api.football-data.org/v4"


class FootballDataClient:
    """one client per pipeline run is plenty. we instantiate fresh
    on each service-layer call rather than holding a long-lived
    singleton, because the rate-limited connection pool doesn't gain
    us anything at our request volume."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.football_data_api_key:
            raise RuntimeError("FOOTBALL_DATA_API_KEY is not set in .env")
        self._headers = {"X-Auth-Token": settings.football_data_api_key}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{BASE_URL}{path}"
        async with httpx.AsyncClient(timeout=20.0, headers=self._headers) as client:
            resp = await client.get(url, params=params)
            # 429 = rate limit. we surface this as a clean error so the
            # caller can retry from cache; we don't loop here because
            # the free tier's per-minute window doesn't reward retries.
            resp.raise_for_status()
            return resp.json()

    async def get_team_fixtures(
        self,
        *,
        status: str | None = None,
        competitions: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """returns united's fixtures, optionally filtered by status
        (scheduled, finished, in_play) or competitions (comma-separated
        codes like 'PL,CL')."""
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if competitions:
            params["competitions"] = competitions
        if limit:
            params["limit"] = limit

        data = await self._get(
            f"/teams/{MANCHESTER_UNITED_TEAM_ID}/matches",
            params=params,
        )
        return data.get("matches", [])

    async def get_competition_standings(self, competition_code: str) -> dict[str, Any]:
        """returns the full league table for a competition. we filter
        to united's row in the repository layer when needed."""
        return await self._get(f"/competitions/{competition_code}/standings")

    async def get_competition_scorers(self, competition_code: str) -> list[dict[str, Any]]:
        """top scorers in a competition. used for 'who is the top
        scorer' / 'how many goals does bruno have' queries."""
        data = await self._get(f"/competitions/{competition_code}/scorers")
        return data.get("scorers", [])