"""turns raw html into clean article text. we're not trying to be clever
here - trafilatura is a well-maintained library that does exactly this
and handles edge cases (paywall snippets, cookie banners, related-articles
sections) better than anything we'd write ourselves."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import trafilatura
from trafilatura.settings import use_config


@dataclass
class ExtractedDocument:
    """what we hand off to the chunker. title and url are mandatory because
    the agent needs them for citations; published_at is best-effort because
    a lot of sites get this wrong."""

    url: str
    title: str
    content: str
    published_at: datetime | None
    author: str | None
    source: str


# trafilatura config. defaults are fine but we explicitly turn off
# its built-in url fetching so we can use our own httpx client with
# proper timeouts and user-agent control.
_TRAFILATURA_CFG = use_config()
_TRAFILATURA_CFG.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")


# a polite but identifiable user-agent. some sites block obvious bots
# (default python-requests), so we look like a desktop browser but with
# a contact line in case anyone wants to reach us.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
    "GafferBot/0.1 (+https://github.com/chukwuemekaorji/gaffer)"
)


async def fetch_html(url: str, *, timeout: float = 30.0) -> str | None:
    """one-shot http fetch. returns the raw html or None if the fetch
    fails. we don't raise here because in the ingestion pipeline a single
    broken url shouldn't kill the whole batch."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except (httpx.HTTPError, httpx.TimeoutException):
        # logged by the caller — we don't want exception noise from every
        # dead link in an rss feed
        return None


def extract(html: str, *, url: str, source: str) -> ExtractedDocument | None:
    """runs trafilatura over the html and packages the result. returns
    None if extraction produced nothing usable (very short content, or
    the page was javascript-rendered with no static text)."""

    # we ask for json output so we get metadata (title, author, date)
    # alongside the body text in a single call.
    raw = trafilatura.extract(
        html,
        output_format="json",
        with_metadata=True,
        include_comments=False,
        include_tables=False,
        favor_precision=True,        # better to miss text than include junk
        config=_TRAFILATURA_CFG,
    )
    if not raw:
        return None

    import json
    data = json.loads(raw)

    text = (data.get("text") or "").strip()
    if len(text) < 200:
        # anything shorter than this is almost always a paywall stub or
        # an extraction failure; not worth the embedding cost.
        return None

    title = (data.get("title") or "").strip() or url
    author = data.get("author")

    # trafilatura's date field is a string in YYYY-MM-DD form when present.
    published_at: datetime | None = None
    if data.get("date"):
        try:
            published_at = datetime.fromisoformat(data["date"]).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            published_at = None

    return ExtractedDocument(
        url=url,
        title=title,
        content=text,
        published_at=published_at,
        author=author,
        source=source,
    )