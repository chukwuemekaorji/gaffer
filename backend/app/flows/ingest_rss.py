"""prefect flow that polls every registered rss feed once.

ran by `prefect.yaml` on a 15-min schedule once deployed. can also
be invoked directly for ad-hoc backfills:

    python -m app.flows.ingest_rss

prefect's flow/task split is what gives us retries, logging, and run
history. one flow per scheduled trigger; one task per logical unit of
work (here: one feed). per-task retry policies handle transient rss
fetch failures without us writing any retry code ourselves."""

from __future__ import annotations

import asyncio

from prefect import flow, get_run_logger, task
from prefect.tasks import exponential_backoff

from app.db.session import SessionLocal
from app.ingestion.rss import FEEDS, FeedSource, PollResult, poll_feed


@task(
    name="poll-rss-feed",
    retries=3,
    retry_delay_seconds=exponential_backoff(backoff_factor=10),
    # exponential backoff: 10s, 20s, 40s. covers most transient flakiness
    # (rss endpoint slow, intermittent dns) without hammering broken feeds.
    tags=["ingestion", "rss"],
)
async def poll_feed_task(feed: FeedSource) -> PollResult:
    log = get_run_logger()
    db = SessionLocal()
    try:
        result = await poll_feed(db, feed)
        log.info(
            "feed=%s ingested=%d skipped=%d failed=%d",
            result.feed, result.ingested, result.skipped, result.failed,
        )
        return result
    finally:
        db.close()


@flow(
    name="ingest-rss-feeds",
    description="polls every registered rss feed and ingests matching entries",
    log_prints=True,
)
async def ingest_rss_flow() -> list[PollResult]:
    log = get_run_logger()
    log.info("polling %d feeds", len(FEEDS))

    # we run feed polls sequentially rather than concurrently. two reasons:
    #   1. embedding api rate limits — too many parallel ingests bursts
    #      voyage's per-minute cap on the free tier.
    #   2. database connection pool — sqlalchemy default pool is 5; running
    #      4 feeds in parallel would saturate it.
    # we can revisit if poll duration becomes a problem.
    results: list[PollResult] = []
    for feed in FEEDS:
        result = await poll_feed_task(feed)
        results.append(result)

    total_ingested = sum(r.ingested for r in results)
    log.info("flow complete — %d new documents ingested", total_ingested)
    return results


if __name__ == "__main__":
    # lets us run the flow directly (without prefect server) for
    # development. when deployed, prefect runs the flow function the
    # same way but with full orchestration around it.
    asyncio.run(ingest_rss_flow())