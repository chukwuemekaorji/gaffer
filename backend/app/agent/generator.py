"""calls claude sonnet to generate the final answer given a built context.

the system prompt is where the 'cite or refuse' guarantee actually
lives. we make it explicit and strict: every claim must reference a
source id; no source id means refuse.

sonnet is the right model here — generation is where output quality
matters most, and the cost is amortised across the cheaper haiku calls
upstream (rewriter + router).

refusals are handled locally (no llm call) with a small category-aware
template bank. fast, free, and the voice stays consistent.

conversation history is threaded through so follow-up turns build on
the previous exchange rather than starting cold each time."""

from __future__ import annotations

import logging
import random
import re
from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from app.agent.context import BuiltContext
from app.agent.schemas import Route, RouterDecision
from app.config import get_settings

log = logging.getLogger(__name__)

GENERATION_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT_TEMPLATE = """you are gaffer, a grounded ai football analyst with manchester united at the centre of your world.

you answer questions about united tactics, players, results, transfers, history, comparisons across managerial eras. you're also conversational about football in general — other clubs, league context, historical players and moments — as long as you can ground what you say.

this is a conversation, not a series of one-shot queries. if you've been talking with this user already, keep that thread going. short follow-ups ('yeah but really', 'what do you think', 'idk', 'i just feel we can do well') are part of the same discussion — answer them in context, don't restate what you've already said. if the user is just vibing about football and not asking a sharp question, vibe back: give your read, ask what they're thinking, keep it natural.

how to handle different question types:

1. factual questions (table position, scores, fixtures) — pull from the structured stats block. cite [Sx]. never invent numbers.

2. tactical analysis — pull from the tactical knowledge base. cite as you go. if the evidence supports multiple readings, say so.

3. recent events (last match, current form, latest news) — pull from the recent news block. cite chronologically. if the corpus is thin, web search results may be present — use them, cite them.

4. speculative / opinion questions ("do you think we can win", "is X overrated", "who's better") — these are fair game. ground your speculation in actual evidence: recent form, head-to-head record, tactical match-up, what the corpus says about the player. always make clear it's your read, not fact. example: "based on recent form [S1] and the way we've handled high pressing this season [S2], i'd lean toward yes — but it's a tight call." never refuse a speculative football question.

5. vibe-shaped follow-ups ('i just feel we can do well', 'we look sharp tho', 'nah we're cooked') — these aren't requests for analysis, they're someone wanting to talk football. match the energy. respond with your own read, anchored in form / squad / context from the conversation. ask them what they're thinking. keep it short and human.

6. questions about other clubs or general football — answer if you have grounding. if the corpus only has thin coverage of, say, arsenal's press, say so plainly and offer what you can. don't pretend to know what you don't.

7. truly off-topic questions (not football at all) — the router will set route=refuse before you see them. you won't need to handle this case.

absolute rules:
- every factual claim must cite a source id like [S1], [S2]. opinions don't need citations, but the form / context they're built on does.
- if the evidence is empty or doesn't address the question, say so plainly and ask for clarification.
- never invent stats, scores, dates, or quotes. these MUST come from the structured stats block or the rag chunks.
- write naturally. no preamble like 'based on the evidence' or 'according to my sources'. just answer and cite as you go.
- when citations span multiple sources, group them: "united pressed high in the first half [S1][S3]." not "...high [S1] in the first half [S3]."
- for stats answers (table, results, fixtures), give the number from the stats block. always cite [Sx] for it.
- don't repeat the user's question back at them before answering. just answer.

format:
- short and direct unless the user asks for depth
- markdown is fine for lists and emphasis
- never include the literal phrase "as an ai"

evidence available:
{context_block}

router reasoning: {router_reasoning}
"""


# ============================================================
# refusal bank
# ============================================================
# each category has a few variants so the bot doesn't feel like a
# stuck record on repeated off-topic prods. all of them follow the
# same shape: acknowledge → make the scope clear → offer something
# i can do. the categories are detected by quick keyword scan, with
# a 'generic' fallback for anything that doesn't match.

REFUSAL_BANK: dict[str, list[str]] = {
    "other_sport": [
        "that's a different sport — i only cover manchester united. ask me about the squad, results, or how carrick's been setting them up and i'm in.",
        "outside my brief, that one. united tactics, players, transfers, recent matches — those i can help with.",
        "not my patch — i'm scoped to manchester united. happy to talk through anything tactical or news-related on the united side.",
    ],
    "other_club": [
        "i'm a united analyst, so i won't go deep on another club. if you want to know how they line up against us though, i can help with that.",
        "i don't cover other clubs in their own right — only how they intersect with united. want me to look at it through that lens?",
        "outside my scope on its own, but if it's about how united match up against them, ask away.",
    ],
    "general_world": [
        "i'm scoped to manchester united — politics, news outside football, that sort of thing isn't what i do. ask me anything united and i'm in.",
        "that's outside my brief. i only cover manchester united — tactics, results, players, transfers.",
        "i don't venture outside the united bubble. give me anything tactical, news, or squad-related on united and i'll have a go.",
    ],
    "personal": [
        "i'm not really set up for that — i'm a united tactical analyst. tactics, results, players, transfers, that's my lane.",
        "outside my brief. i only do manchester united. anything tactical, news, or post-match analysis on the united side?",
    ],
    "generic": [
        "i'm a manchester united analyst — that one's outside my scope. happy to take anything tactical, news, results, or transfers on the united side.",
        "outside my brief, but i'm fully in if you want anything on united — tactics, recent matches, players, table position.",
        "that's not my patch. i'm scoped to manchester united. ask me how carrick's been setting up, how a player's doing, or where we are in the table.",
        "i only cover manchester united. anything else and i'd just be guessing — which i won't do. give me something united-flavoured.",
    ],
}


# keyword sets used to bucket the query. deliberately small — the
# router already decided this is off-topic, all we're doing now is
# picking a flavour of refusal.

_OTHER_SPORTS = {
    "f1", "formula 1", "formula one", "nascar", "indycar",
    "nba", "basketball", "nfl", "american football",
    "mlb", "baseball", "nhl", "hockey",
    "ufc", "mma", "boxing",
    "cricket", "tennis", "wimbledon", "us open", "rugby", "golf", "pga",
    "olympics", "olympic", "athletics",
}

_OTHER_CLUBS = {
    "arsenal", "chelsea", "liverpool", "tottenham", "spurs", "man city", "manchester city",
    "newcastle", "aston villa", "west ham", "everton", "leeds",
    "real madrid", "barcelona", "barca", "atletico", "psg",
    "bayern", "dortmund", "juventus", "inter", "milan", "napoli",
}

_PERSONAL = {
    "you ", "your favourite", "your favorite", "do you like", "are you",
    "love you", "marry me", "your name", "who made you",
}


def _classify_refusal(query: str) -> str:
    q = query.lower()

    for term in _OTHER_SPORTS:
        if term in q:
            return "other_sport"

    # other-club detection only fires when it's *only* about that club —
    # mentions like "how do we play against arsenal" aren't off-topic.
    # crude heuristic: contains a rival but no united-shaped reference.
    united_refs = ("united", "man utd", "manchester united", "we ", "our ", "us ", "ours")
    has_other_club = any(c in q for c in _OTHER_CLUBS)
    has_united = any(u in q for u in united_refs)
    if has_other_club and not has_united:
        return "other_club"

    for term in _PERSONAL:
        if term in q:
            return "personal"

    # generic catch-all for news, life advice, weather, politics, code help, etc.
    return "generic"


def _refusal_for(query: str) -> str:
    category = _classify_refusal(query)
    variants = REFUSAL_BANK.get(category) or REFUSAL_BANK["generic"]
    return random.choice(variants)


# ============================================================
# generation (sonnet) — for grounded answers only
# ============================================================

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set in .env")
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _build_system(context: BuiltContext, decision: RouterDecision) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        context_block=context.prompt_block,
        router_reasoning=decision.reasoning or "n/a",
    )


def _build_messages(query: str, history: list[tuple[str, str]]) -> list[dict]:
    """assemble the anthropic messages array.

    anthropic's api expects strict alternation: user → assistant →
    user → assistant → user. we coerce the history to fit that pattern.
    historic turns slot in as proper roles; the current query is
    always the final user message. this gives sonnet native
    multi-turn context — much better than stuffing prior turns into
    a system-prompt blob, because the model is trained to handle
    conversational structure this way."""
    messages: list[dict] = []
    last_role: str | None = None

    for role, text in history:
        # normalise: only 'user' and 'assistant' are valid for the api.
        api_role = "user" if role == "user" else "assistant"

        # skip empty messages and consecutive same-role turns (shouldn't
        # happen but defends against malformed history from the client).
        if not text.strip():
            continue
        if api_role == last_role:
            continue

        messages.append({"role": api_role, "content": text})
        last_role = api_role

    # the current query is always a fresh user turn. if the last
    # historic message was also a user turn (shouldn't be — assistant
    # always responds last — but defensive code), drop it so we don't
    # send two user turns in a row.
    if messages and messages[-1]["role"] == "user":
        messages.pop()

    messages.append({"role": "user", "content": query})
    return messages


async def generate_stream(
    *,
    query: str,
    context: BuiltContext,
    decision: RouterDecision,
    history: list[tuple[str, str]] | None = None,
) -> AsyncIterator[str]:
    """yields output tokens as they arrive. refusals are served from
    the local bank — no llm call, instant response."""

    # refusal path: no api call, no evidence, no cost. we still yield
    # in chunks so the frontend's streaming render keeps a single code
    # path for all responses.
    if Route.REFUSE in decision.routes and len(decision.routes) == 1:
        text = _refusal_for(query)
        for piece in re.findall(r"\S+\s*", text):
            yield piece
        return

    # normal path: grounded answer over the assembled evidence.
    client = _get_client()
    system = _build_system(context, decision)
    messages = _build_messages(query, history or [])

    async with client.messages.stream(
        model=GENERATION_MODEL,
        max_tokens=1024,
        system=system,
        messages=messages,
        temperature=0.3,
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def generate(
    *,
    query: str,
    context: BuiltContext,
    decision: RouterDecision,
    history: list[tuple[str, str]] | None = None,
) -> str:
    """non-streaming variant for the eval harness. just concatenates
    the stream."""
    chunks: list[str] = []
    async for chunk in generate_stream(
        query=query, context=context, decision=decision, history=history
    ):
        chunks.append(chunk)
    return "".join(chunks)