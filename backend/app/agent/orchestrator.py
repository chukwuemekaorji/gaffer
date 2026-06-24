"""top-level agent entrypoint. runs the full loop: route -> dispatch
-> build context -> generate.

this is the function the `/chat` endpoint calls. it also returns the
sources separately so the frontend can render citations as clickable
references."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agent.context import Source, build_context
from app.agent.dispatcher import dispatch
from app.agent.generator import generate, generate_stream
from app.agent.router import route_query
from app.agent.schemas import RouterDecision

log = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    answer: str
    decision: RouterDecision
    sources: list[Source]
    latency_ms: int


async def answer(db: Session, query: str) -> AgentResponse:
    """blocking variant. used by tests and the eval harness."""
    started = time.perf_counter()

    decision = await route_query(query)
    evidence = await dispatch(db, query, decision)
    context = build_context(evidence)
    text = await generate(query=query, context=context, decision=decision)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return AgentResponse(
        answer=text,
        decision=decision,
        sources=context.sources,
        latency_ms=elapsed_ms,
    )


async def answer_stream(
    db: Session, query: str
) -> AsyncIterator[dict]:
    """streaming variant the api uses. yields a sequence of dicts that
    the api translates into server-sent events:
      {'type': 'decision', 'data': {...}}
      {'type': 'token', 'data': '...'}
      {'type': 'sources', 'data': [...]}
      {'type': 'done', 'data': {'latency_ms': ...}}
    """
    started = time.perf_counter()

    decision = await route_query(query)
    yield {
        "type": "decision",
        "data": {
            "routes": [r.value for r in decision.routes],
            "reasoning": decision.reasoning,
        },
    }

    evidence = await dispatch(db, query, decision)
    context = build_context(evidence)

    # sources first so the ui can render the citations panel while
    # the tokens still stream in.
    yield {
        "type": "sources",
        "data": [
            {
                "id": s.id,
                "kind": s.kind,
                "title": s.title,
                "url": s.url,
                "published_at": str(s.published_at) if s.published_at else None,
            }
            for s in context.sources
        ],
    }

    async for token in generate_stream(query=query, context=context, decision=decision):
        yield {"type": "token", "data": token}

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    yield {"type": "done", "data": {"latency_ms": elapsed_ms}}