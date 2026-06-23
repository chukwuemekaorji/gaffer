"""query rewriting via claude haiku.

motivation: user queries are often short and ambiguous. "how is bruno
playing" gives a semantic embedding that points everywhere — bruno who?
playing where? what season? rewriting expands this into 2-3 variants
that are more retrieval-friendly without changing intent.

we keep the original query in the variant list so a perfectly-worded
query doesn't get diluted by rewrites that are worse than the original."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.config import get_settings

log = logging.getLogger(__name__)

# haiku is more than enough for this. fast, cheap, and rewriting is a
# constrained task — we're not asking for creativity.
REWRITER_MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """you generate retrieval queries for a manchester united tactical analyst.

given a user's question, output 2-3 short reformulations that would be useful for searching a knowledge base of:
- tactical analysis articles (formations, pressing, build-up, transitions)
- match reports
- player profiles
- news and transfers

rules:
- keep reformulations short (under 12 words each)
- add likely synonyms (e.g. 'press' / 'pressing system' / 'high press')
- if the user uses a pronoun or a vague reference, replace with specific terms (man united, the player they mean)
- do not invent facts. if the question is about a player you don't recognise, just rephrase, don't speculate about the player.
- output strict json: {"queries": ["...", "...", "..."]}
- do not output anything outside the json
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


async def rewrite_query(query: str) -> list[str]:
    """returns a list of retrieval-optimised query variants, always
    including the original at index 0. falls back gracefully if the
    llm call fails — we'd rather retrieve with the original query
    than fail the whole pipeline."""

    variants: list[str] = [query]

    try:
        client = _get_client()
        response = await client.messages.create(
            model=REWRITER_MODEL,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
            temperature=0.2,    # low temp — we want predictable rewrites, not creative ones
        )
        raw = response.content[0].text.strip()

        # haiku occasionally wraps json in markdown fences despite the
        # instruction. strip them defensively.
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()

        parsed = json.loads(raw)
        new_variants = [str(q).strip() for q in parsed.get("queries", []) if str(q).strip()]
        # dedupe while preserving order — same query appearing twice
        # would weight it artificially in fusion later
        seen = {query.lower()}
        for v in new_variants:
            if v.lower() not in seen:
                variants.append(v)
                seen.add(v.lower())

    except Exception as exc:
        log.warning("query rewriting failed, falling back to original: %s", exc)

    log.info("rewrote query=%r into %d variants", query, len(variants))
    return variants