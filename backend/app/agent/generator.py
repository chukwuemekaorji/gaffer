"""calls claude sonnet to generate the final answer given a built context.

the system prompt is where the 'cite or refuse' guarantee actually
lives. we make it explicit and strict: every claim must reference a
source id; no source id means refuse.

sonnet is the right model here — generation is where output quality
matters most, and the cost is amortised across the cheaper haiku calls
upstream (rewriter + router)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from app.agent.context import BuiltContext
from app.agent.schemas import Route, RouterDecision
from app.config import get_settings

log = logging.getLogger(__name__)

GENERATION_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT_TEMPLATE = """you are gaffer, a grounded ai tactical analyst for manchester united.

you answer questions about united — tactics, players, results, transfers, post-match analysis, comparisons across managerial eras. you have access to a curated tactical knowledge base, real-time stats, recent news, and web search.

absolute rules:
1. every factual claim must cite a source id like [S1], [S2]. if no source supports a claim, do not make the claim.
2. if the evidence is empty or doesn't address the question, say so plainly and ask the user to clarify or come back when there's more data.
3. never invent stats, scores, dates, or quotes. these MUST come from the structured stats block when present.
4. if the user asks something off-topic (not about united / football tactics / the squad), reply briefly that you're scoped to manchester united and decline.
5. write naturally. no preamble like 'based on the evidence' or 'according to my sources'. just answer the question and cite as you go.
6. when citations span multiple sources, group them: "United pressed high in the first half [S1][S3]." not "...high [S1] in the first half [S3]."
7. for stats answers (table, results, fixtures), give the number from the stats block. always cite [Sx] for it.

format:
- short and direct unless the user asks for depth
- markdown is fine for lists and emphasis
- never include the literal phrase "as an ai"

evidence available:
{context_block}

router reasoning: {router_reasoning}
"""


REFUSE_TEMPLATE = (
    "i'm scoped to manchester united - tactics, results, players, transfers, "
    "post-match analysis. that one's outside my brief. give me anything united "
    "and i'm in."
)


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


async def generate_stream(
    *,
    query: str,
    context: BuiltContext,
    decision: RouterDecision,
) -> AsyncIterator[str]:
    """yields output tokens as they arrive. handles refusal locally so
    we don't burn a sonnet call when the router already decided to refuse."""

    if Route.REFUSE in decision.routes and len(decision.routes) == 1:
        yield REFUSE_TEMPLATE
        return

    client = _get_client()
    system = _build_system(context, decision)

    async with client.messages.stream(
        model=GENERATION_MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": query}],
        temperature=0.3,        # low but not zero — answers should sound natural
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def generate(
    *,
    query: str,
    context: BuiltContext,
    decision: RouterDecision,
) -> str:
    """non-streaming variant for the eval harness. just concatenates
    the stream."""
    chunks: list[str] = []
    async for chunk in generate_stream(query=query, context=context, decision=decision):
        chunks.append(chunk)
    return "".join(chunks)