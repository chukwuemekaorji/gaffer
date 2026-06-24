"""query router. one haiku call decides which retrieval strategies
to dispatch for a given user query.

the router is the single biggest lever in this system. get it right and
the agent never tries to recite a fact from parametric memory — every
factual claim goes through structured stats, every analysis goes through
rag, every recent event has a chance to hit the news corpus. get it wrong
and you've just built a normal chatbot."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.agent.schemas import Route, RouterDecision
from app.config import get_settings

log = logging.getLogger(__name__)

ROUTER_MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """you are the router for gaffer, a grounded ai analyst for manchester united.

your job: given a user query, decide which retrieval strategies to dispatch. you do NOT answer the question. you only classify.

strategies:
- stats: structured lookups for league position, fixtures, scores, results, points totals, goal differences, recent form. use for ANY factual claim about table position, results, or scheduled matches.
- tactical_rag: analysis grounded in tactical articles — formations, pressing, transitions, build-up patterns, set pieces, player roles, comparisons across eras.
- recent_rag: anything about specific recent matches, player performances in specific matches, transfer news, injury reports, press conference quotes from the last few weeks.
- web_search: ONLY for breaking news that may not be indexed yet (today's announcement, breaking transfer in the last 24h). do not use as a default fallback.
- refuse: query is off-topic (not about manchester united, football tactics, or the squad).

rules:
- a query can use MULTIPLE strategies. "how did mainoo play vs liverpool, and where are we in the table" should dispatch [recent_rag, stats].
- never use stats and rag for the SAME fact. stats for the league table; rag for analysis of how the table position came to be.
- extract structured hints if obvious:
  - era: "ten_hag", "amorim", or "carrick" if the query mentions a manager
  - competition: "premier_league", "champions_league", "fa_cup", "efl_cup" if mentioned
  - players: lowercase first-name or last-name tokens, e.g. ["mainoo", "bruno_fernandes"]
  - needs_recency: true if the query is about something recent (last match, this week, recent form)

output strict json:
{
  "routes": ["..."],
  "reasoning": "one short sentence",
  "era": "..." or null,
  "competition": "..." or null,
  "players": ["..."] or [],
  "needs_recency": true or false
}

output nothing outside the json. no markdown fences. no commentary.
"""


_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set in .env")
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


# safe fallback when the router fails. tactical_rag is the most
# generally-applicable strategy, so we default there rather than
# refusing or speculating.
_FALLBACK = RouterDecision(
    routes=[Route.TACTICAL_RAG],
    reasoning="router failed — defaulting to tactical rag",
)


async def route_query(query: str) -> RouterDecision:
    """classify a query into one or more retrieval strategies. never
    raises — failures degrade to a tactical_rag fallback so the agent
    can always make progress."""

    try:
        client = _get_client()
        response = await client.messages.create(
            model=ROUTER_MODEL,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
            temperature=0.0,    # zero temperature — we want deterministic routing
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()

        parsed = json.loads(raw)
        routes_raw = parsed.get("routes") or []
        routes = [Route(r) for r in routes_raw if r in Route._value2member_map_]
        if not routes:
            log.warning("router returned no valid routes, using fallback")
            return _FALLBACK

        decision = RouterDecision(
            routes=routes,
            reasoning=str(parsed.get("reasoning", "")),
            era=parsed.get("era"),
            competition=parsed.get("competition"),
            players=[str(p).lower() for p in (parsed.get("players") or [])],
            needs_recency=bool(parsed.get("needs_recency", False)),
        )
        log.info(
            "routed query=%r routes=%s era=%s players=%s",
            query, [r.value for r in routes], decision.era, decision.players,
        )
        return decision

    except Exception as exc:
        log.warning("router call failed: %s", exc)
        return _FALLBACK