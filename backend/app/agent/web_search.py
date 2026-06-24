"""web search via anthropic's built-in tool.

claude's web_search_20250305 tool runs server-side at anthropic, so we
get high-quality results without us managing a search api key. the
trade-off is we can only invoke it inside a claude message — we can't
call it standalone like a normal http api.

for gaffer's purposes that's fine: web search results land as part of
the message stream and we extract them alongside any text claude
generates."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic

from app.config import get_settings

log = logging.getLogger(__name__)

# haiku is fine for the search step — we're not asking for analysis,
# just for claude to call the tool and report what it found.
SEARCH_MODEL = "claude-haiku-4-5"

# tighten the search to football / united / sports sources by adding
# domain hints to the query. allowed_domains is the right tool here
# because the web_search api supports it natively.
SPORTS_DOMAINS = [
    "bbc.com",
    "bbc.co.uk",
    "manutd.com",
    "skysports.com",
    "theathletic.com",
    "manchestereveningnews.co.uk",
    "theguardian.com",
    "espn.com",
    "transfermarkt.com",
    "premierleague.com",
    "uefa.com",
]


@dataclass
class WebSnippet:
    title: str
    url: str
    content: str
    published_at: str | None = None


@dataclass
class WebSearchResult:
    query: str
    snippets: list[WebSnippet] = field(default_factory=list)
    error: str | None = None


SEARCH_SYSTEM = """you are a search helper. given a query about manchester united,
call the web_search tool and return what you find.

rules:
- always call the web_search tool. do not answer from memory.
- after the search, do not summarise or analyse. just return.
- if the tool returns nothing useful, say so plainly.
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


async def search_web(query: str, *, max_uses: int = 2) -> WebSearchResult:
    """invokes claude with the web search tool and harvests the
    citations / content blocks. returns a structured result so the
    downstream generator can treat web snippets uniformly with rag
    chunks."""

    try:
        client = _get_client()
        response = await client.messages.create(
            model=SEARCH_MODEL,
            max_tokens=1024,
            system=SEARCH_SYSTEM,
            messages=[{"role": "user", "content": query}],
            tools=[
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": max_uses,
                    "allowed_domains": SPORTS_DOMAINS,
                }
            ],
        )

        snippets: list[WebSnippet] = []
        for block in response.content:
            # web_search_tool_result blocks contain the actual results.
            # claude's text blocks are commentary that we ignore here
            # — the downstream generator does the analysis, not this layer.
            if getattr(block, "type", None) == "web_search_tool_result":
                for item in getattr(block, "content", []) or []:
                    if getattr(item, "type", None) != "web_search_result":
                        continue
                    snippets.append(
                        WebSnippet(
                            title=getattr(item, "title", "") or "",
                            url=getattr(item, "url", "") or "",
                            content=getattr(item, "page_age", "") or "",
                            published_at=getattr(item, "page_age", None),
                        )
                    )

        log.info("web search query=%r snippets=%d", query, len(snippets))
        return WebSearchResult(query=query, snippets=snippets)

    except Exception as exc:
        log.warning("web search failed: %s", exc)
        return WebSearchResult(query=query, error=str(exc))