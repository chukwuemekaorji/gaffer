"""query router. one haiku call decides which retrieval strategies
to dispatch for a given user query.

the router is the single biggest lever in this system. get it right and
the agent never tries to recite a fact from parametric memory — every
factual claim goes through structured stats, every analysis goes through
rag, every recent event has a chance to hit the news corpus. get it wrong
and you've just built a normal chatbot.

conversation history is threaded through so short follow-ups
('what do you think', 'yeah but really', 'idk i just feel we can do well')
get classified in the context of the conversation rather than judged
in isolation."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.agent.schemas import Route, RouterDecision
from app.config import get_settings

log = logging.getLogger(__name__)

ROUTER_MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """you are the router for gaffer, an ai analyst grounded in football.

scope:
- PRIMARY focus is manchester united — tactics, players, results, transfers, post-match analysis, history, comparisons across eras.
- SECONDARY: general football is fair game. other clubs, players, historical matches, tactical concepts, league context — all valid as long as they're football. you don't have to refuse just because the question isn't strictly about united.
- OFF-TOPIC and to be refused: anything not football (other sports, weather, news outside football, life advice, code help, philosophy, personal questions about you, etc.).

your job: given a user query, decide which retrieval strategies to dispatch. you do NOT answer the question. you only classify.

context:
- you may be shown recent conversation history before the current message. use it to disambiguate. short or vague follow-ups ('idk', 'what do you think', 'yeah but really', 'i just feel we can do well') are continuations of the previous topic — classify them based on the conversational thread, not the message in isolation.
- if previous turns were about united/football and the current short message is a continuation, the route is the same as the previous turn's topic. do NOT refuse a follow-up just because, read alone, it looks vague.
- only refuse if the current message clearly shifts to a non-football topic.

strategies:
- stats: structured lookups for league position, fixtures, scores, results, points totals, goal differences, recent form. use for ANY factual claim about current standings or scheduled matches.
- tactical_rag: analysis grounded in tactical articles or historical writing — formations, pressing, transitions, build-up patterns, set pieces, player roles, comparisons across eras, history of the club, legendary players or moments.
- recent_rag: anything about specific recent matches, player performances in specific matches, transfer news, injury reports, press conference quotes from the last few weeks.
- web_search: for breaking news that may not be indexed yet (today's announcement, breaking transfer in the last 24h), OR for football questions where the rag corpus likely doesn't have coverage (specific players from other clubs, recent matches of other teams).
- refuse: query is not about football at all.

speculative / opinion questions:
- "do you think we'll win", "what's your prediction", "is X overrated", "who's better" — these are VALID. dispatch [tactical_rag, stats] or [tactical_rag, recent_rag] so the generator can ground a speculative answer in real form / recent matches / tactical context. do NOT refuse opinion-shaped questions about football.
- vibe-shaped follow-ups ('i just feel we can do well', 'we look sharp tho', 'nah we're cooked') are also valid — same routing as opinion questions.

other clubs:
- "how does arsenal press" — valid, dispatch [tactical_rag, web_search]. it's a football question. the generator will ground from what it can find and acknowledge gaps.
- "tell me about messi's barcelona" — valid, dispatch [tactical_rag, web_search].
- only refuse if there's literally no football angle.

rules:
- a query can use MULTIPLE strategies. "how did mainoo play vs liverpool, and where are we in the table" should dispatch [recent_rag, stats].
- extract structured hints if obvious:
  - era: "ferguson", "moyes", "van_gaal", "mourinho", "ole", "rangnick", "ten_hag", "amorim", "carrick" if a united manager is mentioned. null otherwise.
  - competition: "premier_league", "champions_league", "fa_cup", "efl_cup" if mentioned
  - players: lowercase tokens, e.g. ["mainoo", "bruno_fernandes", "cantona"]
  - needs_recency: true if the query is about something recent (last match, this week, recent form, latest news)

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


def _build_user_content(query: str, history: list[tuple[str, str]]) -> str:
    """package history + current query into a single string for the
    router. router context is for disambiguating short follow-ups —
    it doesn't need full assistant responses, just the topic shape.

    we keep this brutally short: last 4 turns, each truncated to 120
    chars. that's enough to recognise 'we were talking about the title
    race' without burning tokens that linearly slow down the router."""
    if not history:
        return query

    lines = ["recent context:"]
    for role, text in history[-4:]:
        speaker = "user" if role == "user" else "gaffer"
        trimmed = text[:120].strip().replace("\n", " ")
        if len(text) > 120:
            trimmed += "..."
        lines.append(f"{speaker}: {trimmed}")
    lines.append(f"current: {query}")
    return "\n".join(lines)


async def route_query(
    query: str,
    *,
    history: list[tuple[str, str]] | None = None,
) -> RouterDecision:
    """classify a query into one or more retrieval strategies. never
    raises — failures degrade to a tactical_rag fallback so the agent
    can always make progress.

    history is optional. when present, it gets prepended to the user
    message so the router can disambiguate short follow-ups based on
    what was being discussed."""

    try:
        client = _get_client()
        user_content = _build_user_content(query, history or [])
        response = await client.messages.create(
            model=ROUTER_MODEL,
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
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
            "routed query=%r routes=%s era=%s players=%s history_turns=%d",
            query, [r.value for r in routes], decision.era, decision.players,
            len(history or []),
        )
        return decision

    except Exception as exc:
        log.warning("router call failed: %s", exc)
        return _FALLBACK