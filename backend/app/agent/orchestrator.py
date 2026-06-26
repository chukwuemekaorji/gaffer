"""top-level agent entrypoint. runs the full loop: route -> dispatch
-> build context -> generate.

now wrapped with three observability layers:
  - semantic cache (redis): skip everything for near-duplicate queries
  - langfuse traces: per-stage timing + payloads for debugging
  - query log (postgres): sql-queryable analytics on every query

conversation history is threaded through router and generator so
follow-up turns ('what do you think', 'yeah but really') get
classified and answered in the context of the conversation, not in
isolation.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agent.context import Source, build_context
from app.agent.dispatcher import dispatch
from app.agent.generator import generate, generate_stream
from app.agent.router import route_query
from app.agent.schemas import Route, RouterDecision
from app.obs import cache, query_log
from app.obs.langfuse_client import get_langfuse

log = logging.getLogger(__name__)


# how many prior turns the router and generator see. enough to anchor
# context, small enough to keep token costs predictable. older turns
# slide off the window — the conversation gets 'recent memory' rather
# than infinite recall.
HISTORY_WINDOW = 8


@dataclass
class AgentResponse:
    answer: str
    decision: RouterDecision
    sources: list[Source]
    latency_ms: int
    cache_hit: bool = False


def _serialise_sources(sources: list[Source]) -> str:
    return json.dumps(
        [
            {
                "id": s.id,
                "kind": s.kind,
                "title": s.title,
                "url": s.url,
                "published_at": str(s.published_at) if s.published_at else None,
            }
            for s in sources
        ]
    )


def _deserialise_sources(raw: str) -> list[Source]:
    data = json.loads(raw)
    return [
        Source(
            id=item["id"],
            kind=item["kind"],
            title=item["title"],
            url=item.get("url"),
            published_at=item.get("published_at"),
        )
        for item in data
    ]


def _serialise_decision(decision: RouterDecision) -> str:
    return json.dumps(
        {
            "routes": [r.value for r in decision.routes],
            "reasoning": decision.reasoning,
            "era": decision.era,
            "competition": decision.competition,
            "players": decision.players,
            "needs_recency": decision.needs_recency,
        }
    )


def _deserialise_decision(raw: str) -> RouterDecision:
    data = json.loads(raw)
    return RouterDecision(
        routes=[Route(r) for r in data["routes"]],
        reasoning=data.get("reasoning", ""),
        era=data.get("era"),
        competition=data.get("competition"),
        players=data.get("players") or [],
        needs_recency=bool(data.get("needs_recency", False)),
    )


def _cache_key(query: str, history: list[tuple[str, str]]) -> str:
    """build the string we hand to the cache for similarity lookup.

    for a one-shot query, this is just the query. for a follow-up, we
    prepend a compact summary of recent turns so the cache understands
    'yeah but really' after a carrick conversation is a different
    query than the same words after a cantona conversation.

    we keep this lightweight — just the last couple of turns,
    truncated. the semantic cache embeds this string, so longer
    context = noisier embeddings, not better matches."""
    if not history:
        return query

    tail = history[-4:]
    parts = []
    for role, text in tail:
        speaker = "user" if role == "user" else "gaffer"
        snippet = text[:200].strip().replace("\n", " ")
        parts.append(f"{speaker}: {snippet}")
    return " | ".join(parts) + f" || current: {query}"


async def answer(
    db: Session,
    query: str,
    *,
    history: list[tuple[str, str]] | None = None,
) -> AgentResponse:
    """blocking variant. used by tests and the eval harness. the
    streaming variant below shares all the observability + cache logic
    via duck typing on the events it yields."""
    started = time.perf_counter()
    history = history or []
    history = history[-HISTORY_WINDOW:]

    lf = get_langfuse()
    trace = lf.trace(name="gaffer-agent", input={"query": query, "history_turns": len(history)}) if lf else None

    cache_key = _cache_key(query, history)

    # ---- cache lookup ----
    cached = await cache.lookup(cache_key)
    if cached:
        decision = _deserialise_decision(cached.decision_json)
        sources = _deserialise_sources(cached.sources_json)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if trace:
            trace.update(output={"cache_hit": True, "answer": cached.answer})
        query_log.log_query(
            db,
            user_query=query,
            routes=[r.value for r in decision.routes],
            retrieved_chunk_ids=None,
            cache_hit=True,
            web_search_used=False,
            answer=cached.answer,
            latency_ms=elapsed_ms,
        )
        return AgentResponse(
            answer=cached.answer,
            decision=decision,
            sources=sources,
            latency_ms=elapsed_ms,
            cache_hit=True,
        )

    # ---- route ----
    if trace:
        route_span = trace.span(name="route")
    decision = await route_query(query, history=history)
    if trace:
        route_span.update(
            output={
                "routes": [r.value for r in decision.routes],
                "reasoning": decision.reasoning,
                "era": decision.era,
                "players": decision.players,
            }
        )
        route_span.end()

    # ---- dispatch ----
    if trace:
        dispatch_span = trace.span(name="dispatch")
    evidence = await dispatch(db, query, decision)
    if trace:
        dispatch_span.update(
            output={
                "tactical_count": len(evidence.tactical.candidates) if evidence.tactical else 0,
                "recent_count": len(evidence.recent.candidates) if evidence.recent else 0,
                "stats_present": evidence.stats is not None,
                "web_snippets": len(evidence.web.snippets) if evidence.web else 0,
            }
        )
        dispatch_span.end()

    # ---- build context ----
    context = build_context(evidence)

    # ---- generate ----
    if trace:
        gen_span = trace.span(name="generate")
    text = await generate(query=query, context=context, decision=decision, history=history)
    if trace:
        gen_span.update(output={"answer_length": len(text), "n_sources": len(context.sources)})
        gen_span.end()

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    # ---- store in cache + write query log ----
    chunk_ids: list[int] = []
    if evidence.tactical:
        chunk_ids.extend(c.chunk_id for c in evidence.tactical.candidates)
    if evidence.recent:
        chunk_ids.extend(c.chunk_id for c in evidence.recent.candidates)

    web_used = evidence.web is not None and bool(evidence.web.snippets)

    await cache.store(
        query=cache_key,
        answer=text,
        sources_json=_serialise_sources(context.sources),
        decision_json=_serialise_decision(decision),
        latency_ms=elapsed_ms,
    )

    query_log.log_query(
        db,
        user_query=query,
        routes=[r.value for r in decision.routes],
        retrieved_chunk_ids=chunk_ids,
        cache_hit=False,
        web_search_used=web_used,
        answer=text,
        latency_ms=elapsed_ms,
    )

    if trace:
        trace.update(output={"cache_hit": False, "answer": text})

    return AgentResponse(
        answer=text,
        decision=decision,
        sources=context.sources,
        latency_ms=elapsed_ms,
    )


async def answer_stream(
    db: Session,
    query: str,
    *,
    history: list[tuple[str, str]] | None = None,
) -> AsyncIterator[dict]:
    """streaming variant for the chat ui. emits sse-style events.

    cache hits get replayed as a single 'token' event with the full
    cached text — the frontend renders it the same way as a streamed
    response."""
    started = time.perf_counter()
    history = history or []
    history = history[-HISTORY_WINDOW:]

    lf = get_langfuse()
    trace = lf.trace(name="gaffer-agent-stream", input={"query": query, "history_turns": len(history)}) if lf else None

    cache_key = _cache_key(query, history)

    # cache fast path
    cached = await cache.lookup(cache_key)
    if cached:
        decision = _deserialise_decision(cached.decision_json)
        sources = _deserialise_sources(cached.sources_json)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        yield {
            "type": "decision",
            "data": {
                "routes": [r.value for r in decision.routes],
                "reasoning": f"{decision.reasoning} (served from cache)",
            },
        }
        yield {
            "type": "sources",
            "data": [
                {
                    "id": s.id,
                    "kind": s.kind,
                    "title": s.title,
                    "url": s.url,
                    "published_at": s.published_at,
                }
                for s in sources
            ],
        }
        yield {"type": "token", "data": cached.answer}
        yield {"type": "done", "data": {"latency_ms": elapsed_ms, "cache_hit": True}}

        query_log.log_query(
            db,
            user_query=query,
            routes=[r.value for r in decision.routes],
            retrieved_chunk_ids=None,
            cache_hit=True,
            web_search_used=False,
            answer=cached.answer,
            latency_ms=elapsed_ms,
        )
        if trace:
            trace.update(output={"cache_hit": True})
        return

    # full pipeline
    if trace:
        route_span = trace.span(name="route")
    decision = await route_query(query, history=history)
    if trace:
        route_span.update(output={"routes": [r.value for r in decision.routes]})
        route_span.end()

    yield {
        "type": "decision",
        "data": {
            "routes": [r.value for r in decision.routes],
            "reasoning": decision.reasoning,
        },
    }

    if trace:
        dispatch_span = trace.span(name="dispatch")
    evidence = await dispatch(db, query, decision)
    if trace:
        dispatch_span.end()

    context = build_context(evidence)

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

    if trace:
        gen_span = trace.span(name="generate")

    answer_chunks: list[str] = []
    async for token in generate_stream(query=query, context=context, decision=decision, history=history):
        answer_chunks.append(token)
        yield {"type": "token", "data": token}

    full_answer = "".join(answer_chunks)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if trace:
        gen_span.update(output={"answer_length": len(full_answer)})
        gen_span.end()
        trace.update(output={"cache_hit": False, "answer": full_answer})

    chunk_ids: list[int] = []
    if evidence.tactical:
        chunk_ids.extend(c.chunk_id for c in evidence.tactical.candidates)
    if evidence.recent:
        chunk_ids.extend(c.chunk_id for c in evidence.recent.candidates)
    web_used = evidence.web is not None and bool(evidence.web.snippets)

    await cache.store(
        query=cache_key,
        answer=full_answer,
        sources_json=_serialise_sources(context.sources),
        decision_json=_serialise_decision(decision),
        latency_ms=elapsed_ms,
    )

    query_log.log_query(
        db,
        user_query=query,
        routes=[r.value for r in decision.routes],
        retrieved_chunk_ids=chunk_ids,
        cache_hit=False,
        web_search_used=web_used,
        answer=full_answer,
        latency_ms=elapsed_ms,
    )

    yield {"type": "done", "data": {"latency_ms": elapsed_ms, "cache_hit": False}}