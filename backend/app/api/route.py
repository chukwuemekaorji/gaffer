"""api endpoint that runs only the router. handy for sanity-checking
which strategy gets picked for any given query, without actually
dispatching the downstream retrieval."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.agent.router import route_query

router = APIRouter(prefix="/route", tags=["agent"])


class RouteRequest(BaseModel):
    query: str


@router.post("")
async def route_endpoint(req: RouteRequest):
    decision = await route_query(req.query)
    return {
        "routes": [r.value for r in decision.routes],
        "reasoning": decision.reasoning,
        "era": decision.era,
        "competition": decision.competition,
        "players": decision.players,
        "needs_recency": decision.needs_recency,
    }