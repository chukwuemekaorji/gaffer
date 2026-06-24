"""api endpoints exposing the stats service. mostly for development
testing — the real consumer is the agent."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.stats import service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/next-fixture")
async def next_fixture(db: Session = Depends(get_db)):
    return await service.get_next_fixture(db)


@router.get("/recent-results")
async def recent_results(limit: int = 5, db: Session = Depends(get_db)):
    return await service.get_recent_results(db, limit=limit)


@router.get("/upcoming")
async def upcoming(limit: int = 5, db: Session = Depends(get_db)):
    return await service.get_upcoming_fixtures(db, limit=limit)


@router.get("/table-position")
async def table_position(competition: str = "premier_league", db: Session = Depends(get_db)):
    return await service.get_table_position(db, competition=competition)


@router.get("/table")
async def table(competition: str = "premier_league", db: Session = Depends(get_db)):
    return await service.get_full_table(db, competition=competition)