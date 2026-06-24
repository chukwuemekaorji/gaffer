"""writes and reads structured stats from postgres. acts as a cache
between the football-data api and the agent — minutes-stale data is
totally fine for 'when is the next fixture' or 'what's our table
position'."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


# how stale data can be before we refresh from the upstream api. these
# are agent-facing defaults — a flow that explicitly forces a refresh
# can bypass them.
FIXTURE_STALENESS = timedelta(minutes=30)
TABLE_STALENESS = timedelta(hours=1)


def upsert_fixtures(db: Session, matches: list[dict[str, Any]]) -> int:
    """upserts fixtures from football-data's match payload. returns
    the number of rows touched. uses external_id (football-data's
    match id) as the upsert key so re-running is idempotent."""

    if not matches:
        return 0

    params = []
    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        params.append(
            {
                "external_id": m["id"],
                "competition": m.get("competition", {}).get("code", "").lower() or "unknown",
                "season": str(m.get("season", {}).get("startDate", "")[:4] or ""),
                "matchday": m.get("matchday"),
                "kickoff_utc": m["utcDate"],
                "home_team": m["homeTeam"]["name"],
                "away_team": m["awayTeam"]["name"],
                "home_score": score.get("home"),
                "away_score": score.get("away"),
                "status": (m.get("status") or "").lower(),
                "venue": m.get("venue"),
            }
        )

    db.execute(
        text(
            """
            insert into fixtures (
                external_id, competition, season, matchday, kickoff_utc,
                home_team, away_team, home_score, away_score, status, venue
            ) values (
                :external_id, :competition, :season, :matchday, :kickoff_utc,
                :home_team, :away_team, :home_score, :away_score, :status, :venue
            )
            on conflict (external_id) do update set
                competition = excluded.competition,
                home_score  = excluded.home_score,
                away_score  = excluded.away_score,
                status      = excluded.status,
                updated_at  = now()
            """
        ),
        params,
    )
    db.commit()
    return len(params)


def get_next_fixture(db: Session) -> dict[str, Any] | None:
    """the next scheduled fixture across all competitions."""
    row = db.execute(
        text(
            """
            select * from fixtures
            where status in ('scheduled', 'timed')
              and kickoff_utc > now()
            order by kickoff_utc asc
            limit 1
            """
        )
    ).mappings().first()
    return dict(row) if row else None


def get_recent_results(db: Session, limit: int = 5) -> list[dict[str, Any]]:
    """most recent finished fixtures, newest first. 5 is the standard
    'last 5 games' form indicator."""
    rows = db.execute(
        text(
            """
            select * from fixtures
            where status = 'finished'
            order by kickoff_utc desc
            limit :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_upcoming_fixtures(db: Session, limit: int = 5) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            select * from fixtures
            where status in ('scheduled', 'timed')
              and kickoff_utc > now()
            order by kickoff_utc asc
            limit :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def upsert_league_table(
    db: Session,
    *,
    competition_code: str,
    season: str,
    standings_payload: dict[str, Any],
) -> int:
    """parses a football-data standings response and upserts it into
    league_table. wipes prior rows for the same (competition, season)
    so we don't carry stale teams forward."""

    # football-data returns a list of 'standings' (e.g. total, home, away).
    # we want the 'TOTAL' one.
    table_rows: list[dict[str, Any]] = []
    for s in standings_payload.get("standings", []):
        if s.get("type") != "TOTAL":
            continue
        table_rows = s.get("table", [])
        break

    if not table_rows:
        return 0

    # wipe before insert. simpler than diffing.
    db.execute(
        text(
            "delete from league_table where competition = :competition and season = :season"
        ),
        {"competition": competition_code.lower(), "season": season},
    )

    params = []
    for row in table_rows:
        params.append(
            {
                "competition": competition_code.lower(),
                "season": season,
                "position": row["position"],
                "team": row["team"]["name"],
                "played": row["playedGames"],
                "won": row["won"],
                "drawn": row["draw"],
                "lost": row["lost"],
                "goals_for": row["goalsFor"],
                "goals_against": row["goalsAgainst"],
                "goal_difference": row["goalDifference"],
                "points": row["points"],
                "form": (row.get("form") or "").replace(",", "").lower() or None,
            }
        )

    db.execute(
        text(
            """
            insert into league_table (
                competition, season, position, team,
                played, won, drawn, lost,
                goals_for, goals_against, goal_difference, points, form
            ) values (
                :competition, :season, :position, :team,
                :played, :won, :drawn, :lost,
                :goals_for, :goals_against, :goal_difference, :points, :form
            )
            on conflict (competition, season, team) do update set
                position = excluded.position,
                played   = excluded.played,
                won      = excluded.won,
                drawn    = excluded.drawn,
                lost     = excluded.lost,
                goals_for = excluded.goals_for,
                goals_against = excluded.goals_against,
                goal_difference = excluded.goal_difference,
                points   = excluded.points,
                form     = excluded.form,
                updated_at = now()
            """
        ),
        params,
    )
    db.commit()
    return len(params)


def get_team_table_row(
    db: Session, *, competition: str, season: str, team_substring: str = "Manchester United"
) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            select * from league_table
            where competition = :competition
              and season = :season
              and team ilike :team
            limit 1
            """
        ),
        {"competition": competition.lower(), "season": season, "team": f"%{team_substring}%"},
    ).mappings().first()
    return dict(row) if row else None


def get_full_table(
    db: Session, *, competition: str, season: str
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            select * from league_table
            where competition = :competition and season = :season
            order by position asc
            """
        ),
        {"competition": competition.lower(), "season": season},
    ).mappings().all()
    return [dict(r) for r in rows]


def league_table_age(db: Session, *, competition: str, season: str) -> timedelta | None:
    """how old the cached table is, for staleness checks. None means
    we've never cached this competition+season."""
    row = db.execute(
        text(
            """
            select max(updated_at) as updated_at from league_table
            where competition = :competition and season = :season
            """
        ),
        {"competition": competition.lower(), "season": season},
    ).first()
    if not row or not row[0]:
        return None
    return datetime.now(timezone.utc) - row[0]


def fixtures_age(db: Session) -> timedelta | None:
    row = db.execute(text("select max(updated_at) from fixtures")).first()
    if not row or not row[0]:
        return None
    return datetime.now(timezone.utc) - row[0]