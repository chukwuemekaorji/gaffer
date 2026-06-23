"""rss feed registry + poller.

the registry is just python data — no yaml, no database. feeds change
rarely enough that editing this file when we add one is fine, and
keeping it as code means we can attach defaults (per-source era hints,
default topic tags) without inventing a config schema."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import feedparser
import httpx
from sqlalchemy.orm import Session

from app.ingestion.extractor import USER_AGENT
from app.ingestion.pipeline import ingest_url
from app.ingestion.repository import ChunkMetadata

log = logging.getLogger(__name__)


@dataclass
class FeedSource:
    """one rss feed plus the metadata we apply to everything ingested
    from it. era/season default to the current ones; we'll add per-entry
    overrides later when we want to backfill historical content."""

    name: str                       # short id used in the db (e.g. 'manutd_official')
    url: str
    doc_type: str = "news"          # most rss feeds are news; tactical sources override this
    default_era: str | None = "carrick"
    default_season: str | None = "2025-26"
    default_topic: str | None = None
    # entries whose titles or summaries contain any of these terms get
    # ingested; everything else gets skipped. lets us subscribe to broad
    # feeds (bbc sport football) without ingesting every premier league
    # article. set to None to ingest everything.
    keyword_filter: list[str] | None = field(
        default_factory=lambda: ["manchester united", "man utd", "united"]
    )


# the actual registry. add a new FeedSource and the poller picks it up
# on the next run — no further wiring needed.
FEEDS: list[FeedSource] = [
    FeedSource(
        name="bbc_sport_football",
        url="https://feeds.bbci.co.uk/sport/football/rss.xml",
        doc_type="news",
    ),
    FeedSource(
        name="manutd_official",
        url="https://www.manutd.com/en/rss-feeds/news",
        doc_type="news",
        keyword_filter=None,        # everything on the official site is united
    ),
    FeedSource(
        name="guardian_football",
        url="https://www.theguardian.com/football/rss",
        doc_type="news",
    ),
    FeedSource(
        name="manchester_evening_news",
        url="https://www.manchestereveningnews.co.uk/sport/football/football-news/?service=rss",
        doc_type="news",
    ),
]


@dataclass
class PollResult:
    feed: str
    entries_seen: int
    entries_matched: int
    ingested: int
    skipped: int
    failed: int


async def fetch_feed(url: str, *, timeout: float = 20.0) -> feedparser.FeedParserDict | None:
    """fetch raw rss with our own httpx client, then hand the bytes to
    feedparser. doing our own fetch (vs feedparser.parse(url)) means we
    control the user-agent and timeout. some sites 403 the default
    feedparser ua."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return feedparser.parse(resp.content)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        log.warning("rss fetch failed url=%s err=%s", url, exc)
        return None


def _matches_filter(entry: dict, terms: list[str] | None) -> bool:
    if not terms:
        return True
    haystack = " ".join(
        [
            entry.get("title", ""),
            entry.get("summary", ""),
            entry.get("description", ""),
        ]
    ).lower()
    return any(term.lower() in haystack for term in terms)


def _entry_url(entry: dict) -> str | None:
    # rss entries put the canonical url in 'link' but some feeds use
    # 'id' or 'guid' that happens to be a url. fall back gracefully.
    for key in ("link", "id", "guid"):
        value = entry.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return None


async def poll_feed(db: Session, feed: FeedSource, *, max_entries: int = 25) -> PollResult:
    """polls one feed and runs each matching entry through ingest_url.
    dedup is handled inside the pipeline (by url), so re-running this
    every 15 minutes is safe."""

    parsed = await fetch_feed(feed.url)
    if parsed is None:
        return PollResult(feed.name, 0, 0, 0, 0, 1)

    entries = list(parsed.entries)[:max_entries]
    matched = 0
    ingested = 0
    skipped = 0
    failed = 0

    for entry in entries:
        if not _matches_filter(entry, feed.keyword_filter):
            continue
        matched += 1

        url = _entry_url(entry)
        if url is None:
            skipped += 1
            continue

        metadata = ChunkMetadata(
            era=feed.default_era,
            season=feed.default_season,
            topic=feed.default_topic,
        )

        try:
            result = await ingest_url(
                db,
                url=url,
                source=feed.name,
                doc_type=feed.doc_type,
                metadata=metadata,
            )
            if result.skipped:
                skipped += 1
            else:
                ingested += 1
        except Exception as exc:
            # swallow per-entry exceptions so one broken article doesn't
            # kill the whole feed. prefect will surface this in the run
            # history if the failure count gets too high.
            log.exception("ingestion failed url=%s err=%s", url, exc)
            failed += 1

    log.info(
        "polled feed=%s seen=%d matched=%d ingested=%d skipped=%d failed=%d",
        feed.name, len(entries), matched, ingested, skipped, failed,
    )
    return PollResult(feed.name, len(entries), matched, ingested, skipped, failed)