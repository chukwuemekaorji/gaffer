"""writes to the local query_log table. complements langfuse (which is
the rich trace store) by giving us sql-queryable telemetry:

  - how many queries hit the cache vs miss
  - average latency by route
  - which queries trigger refusals
  - cost per day

we keep this very narrow — log one row per query, no per-step rows.
langfuse handles the deep traces."""

from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def log_query(
    db: Session,
    *,
    user_query: str,
    routes: Sequence[str],
    retrieved_chunk_ids: Sequence[int] | None,
    cache_hit: bool,
    web_search_used: bool,
    answer: str,
    latency_ms: int,
    total_input_tokens: int | None = None,
    total_output_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
) -> None:
    """fire-and-forget insert. swallows errors so a logging failure
    never breaks the actual user response."""
    try:
        db.execute(
            text(
                """
                insert into query_log (
                    user_query, route, retrieved_chunk_ids,
                    cache_hit, web_search_used, answer, latency_ms,
                    total_input_tokens, total_output_tokens, estimated_cost_usd
                )
                values (
                    :user_query, :route, :retrieved_chunk_ids,
                    :cache_hit, :web_search_used, :answer, :latency_ms,
                    :total_input_tokens, :total_output_tokens, :estimated_cost_usd
                )
                """
            ),
            {
                "user_query": user_query,
                "route": list(routes),
                "retrieved_chunk_ids": list(retrieved_chunk_ids or []),
                "cache_hit": cache_hit,
                "web_search_used": web_search_used,
                "answer": answer,
                "latency_ms": latency_ms,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "estimated_cost_usd": estimated_cost_usd,
            },
        )
        db.commit()
    except Exception as exc:
        # logging shouldn't block the user response
        log.warning("query_log insert failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass