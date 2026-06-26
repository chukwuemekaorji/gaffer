"""one-shot batch ingester for the historical united corpus.

seeds 20 curated articles spanning busby → amorim. each entry carries
its own metadata so the chunks land with proper era / topic / player
tags, which the router then uses to filter retrieval.

usage:
    python -m scripts.ingest_historical

it's deliberately resumable: if an article was ingested in a previous
run (duplicate_url), the pipeline skips it cleanly. you can re-run
this as many times as you want without polluting the corpus.

if a single article fails (network, extraction, embedding api), we
log it and keep going — one bad url shouldn't tank the whole batch.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.db.session import SessionLocal
from app.ingestion.pipeline import ingest_url
from app.ingestion.repository import ChunkMetadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@dataclass
class CorpusEntry:
    """one article to ingest with its metadata. each field maps directly
    to a column or tag on the chunks table, so the router can filter
    on these later."""
    url: str
    source: str
    doc_type: str
    era: str | None = None
    topic: str | None = None
    players: list[str] | None = None
    competition: str | None = None


# the corpus, organised by era for readability. order doesn't matter
# at runtime — the script will fire them in this order but the
# pipeline is idempotent so reruns produce no duplicates.

CORPUS: list[CorpusEntry] = [
    # ---------------------- busby (1945–1969) ----------------------
    CorpusEntry(
        url="https://www.manutd.com/en/history/munich-remembered/the-busby-babes",
        source="manutd_official",
        doc_type="tactical_primer",
        era="ferguson",  # we use 'ferguson' as the catch-all pre-1986 era since the router enum doesn't have 'busby' yet
        topic="club_history",
        players=["busby", "duncan_edwards", "bobby_charlton"],
    ),
    CorpusEntry(
        url="https://www.si.com/soccer/man-utd-trailblazing-busby-babes-everlasting-legacy",
        source="sports_illustrated",
        doc_type="tactical_primer",
        era="ferguson",
        topic="club_history",
        players=["busby", "duncan_edwards", "bobby_charlton"],
    ),
    CorpusEntry(
        url="https://en.wikipedia.org/wiki/Matt_Busby",
        source="wikipedia",
        doc_type="player_profile",
        era="ferguson",
        topic="club_history",
        players=["busby"],
    ),

    # ---------------- early ferguson + cantona (1986–1996) ----------------
    CorpusEntry(
        url="https://en.wikipedia.org/wiki/Eric_Cantona",
        source="wikipedia",
        doc_type="player_profile",
        era="ferguson",
        topic="player_legacy",
        players=["cantona"],
    ),
    CorpusEntry(
        url="https://learning.coachesvoice.com/cv/rene-meulensteen-alex-ferguson-tactics/",
        source="coaches_voice",
        doc_type="tactical_primer",
        era="ferguson",
        topic="tactical_principles",
        players=["ferguson"],
    ),
    CorpusEntry(
        url="https://www.goal.com/story/eric-cantona-celebrates-manchester-united-anniversary/index.html",
        source="goal",
        doc_type="player_profile",
        era="ferguson",
        topic="player_legacy",
        players=["cantona"],
    ),
    CorpusEntry(
        url="https://mufchub.com/blog/the-king-of-old-trafford-eric-cantona-s-legendary-spell-at-manchester-united",
        source="mufchub",
        doc_type="player_profile",
        era="ferguson",
        topic="player_legacy",
        players=["cantona"],
    ),

    # ---------------- treble year & class of 92 (1996–1999) ----------------
    CorpusEntry(
        url="https://www.tntsports.co.uk/football/champions-league/2018-2019/manchester-united-and-the-1998-99-treble-that-night-in-barcelona_sto7286033/story.shtml",
        source="tnt_sports",
        doc_type="match_report",
        era="ferguson",
        topic="champions_league",
        players=["sheringham", "solskjaer", "schmeichel", "beckham"],
        competition="champions_league",
    ),
    CorpusEntry(
        url="https://ristogjorgjiev.com/2025/01/29/sir-alex-fergusons-treble-winning-masterclass-the-tactical-brilliance-behind-manchester-uniteds-1998-99-historic-season/",
        source="independent_blog",
        doc_type="tactical_primer",
        era="ferguson",
        topic="treble_season",
        players=["keane", "scholes", "stam", "yorke", "cole"],
    ),
    CorpusEntry(
        url="https://en.wikipedia.org/wiki/1998%E2%80%9399_Manchester_United_F.C._season",
        source="wikipedia",
        doc_type="match_report",
        era="ferguson",
        topic="treble_season",
        players=["sheringham", "solskjaer", "schmeichel", "keane", "beckham", "stam"],
        competition="champions_league",
    ),

    # ---------------- ronaldo / 2008 era (2003–2009) ----------------
    CorpusEntry(
        url="https://www.mancunianmatters.co.uk/sport/21042020-analysis-a-tactical-review-of-the-2008-champions-league-final-manchester-uniteds-moscow-triumph/",
        source="mancunian_matters",
        doc_type="match_report",
        era="ferguson",
        topic="champions_league",
        players=["ronaldo", "tevez", "rooney", "van_der_sar"],
        competition="champions_league",
    ),
    CorpusEntry(
        url="https://thefalse9.com/2017/03/tactical-analysis-manchester-united-200708-premier-league-champions-league-winners.html",
        source="the_false_nine",
        doc_type="tactical_primer",
        era="ferguson",
        topic="formation",
        players=["ronaldo", "tevez", "rooney", "carrick", "scholes"],
    ),

    # ---------------- mourinho era (2016–2018) ----------------
    CorpusEntry(
        url="https://en.wikipedia.org/wiki/Jos%C3%A9_Mourinho",
        source="wikipedia",
        doc_type="player_profile",
        era="mourinho",
        topic="tactical_principles",
        players=["mourinho"],
    ),
    CorpusEntry(
        url="https://www.holdingmidfield.com/whats-going-wrong-at-manchester-united/",
        source="holding_midfield",
        doc_type="tactical_primer",
        era="mourinho",
        topic="tactical_principles",
        players=["pogba", "lukaku", "sanchez"],
    ),
    CorpusEntry(
        url="https://www.irishtimes.com/sport/soccer/english-soccer/ken-early-mourinho-s-tactics-undermine-pogba-and-sanchez-1.3431976",
        source="irish_times",
        doc_type="tactical_primer",
        era="mourinho",
        topic="tactical_principles",
        players=["pogba", "sanchez", "mourinho"],
    ),

    # ---------------- ole era (2018–2021) ----------------
    CorpusEntry(
        url="https://en.wikipedia.org/wiki/Ole_Gunnar_Solskj%C3%A6r",
        source="wikipedia",
        doc_type="player_profile",
        era="ole",
        topic="tactical_principles",
        players=["solskjaer"],
    ),

    # ---------------- ten hag era (2022–2024) ----------------
    CorpusEntry(
        url="https://www.premierleague.com/en/news/4160580",
        source="premier_league",
        doc_type="tactical_primer",
        era="ten_hag",
        topic="formation",
        players=["fernandes", "martinez", "garnacho"],
    ),

    # ---------------- amorim era (2024–) ----------------
    CorpusEntry(
        url="https://thefalse9.com/2024/10/man-united-formation-tactics-ruben-amorim.html",
        source="the_false_nine",
        doc_type="tactical_primer",
        era="amorim",
        topic="formation",
        players=["fernandes", "ugarte", "martinez"],
    ),
    CorpusEntry(
        url="https://www.skysports.com/football/news/11661/13321126/ruben-amorims-man-utd-tactics-will-3-4-3-formation-ever-work-for-head-coach-at-old-trafford",
        source="sky_sports",
        doc_type="tactical_primer",
        era="amorim",
        topic="formation",
        players=["fernandes", "amorim"],
    ),
    CorpusEntry(
        url="https://totalfootballanalysis.com/head-coach-analysis/ruben-amorim-manchester-united-tactical-analysis-tactics",
        source="total_football_analysis",
        doc_type="tactical_primer",
        era="amorim",
        topic="formation",
        players=["fernandes", "ugarte", "garnacho", "amorim"],
    ),
]


async def main() -> int:
    log.info("=== gaffer historical corpus seed ===")
    log.info("articles to process: %d", len(CORPUS))

    n_ingested = 0
    n_skipped = 0
    n_failed = 0

    # we use a fresh session per article so a single transactional error
    # doesn't poison the rest of the run. ingestion is i/o-bound (network
    # + voyage + supabase) so the overhead is negligible.
    for i, entry in enumerate(CORPUS, start=1):
        log.info("[%d/%d] %s", i, len(CORPUS), entry.url)
        metadata = ChunkMetadata(
            era=entry.era,
            topic=entry.topic,
            players_mentioned=entry.players,
            competition=entry.competition,
        )

        db = SessionLocal()
        try:
            result = await ingest_url(
                db,
                url=entry.url,
                source=entry.source,
                doc_type=entry.doc_type,
                metadata=metadata,
            )
            if result.skipped:
                log.info("    skipped: %s", result.reason)
                n_skipped += 1
            else:
                log.info("    ok: document_id=%s chunks=%d",
                         result.document_id, result.chunks_inserted)
                n_ingested += 1
        except Exception as exc:
            # log + continue. common failures: trafilatura extraction
            # returning empty (page is js-rendered, hit a 403, etc), or
            # voyage hitting a transient rate limit.
            log.warning("    failed: %s", exc)
            n_failed += 1
        finally:
            db.close()

        # voyage free-tier rate limit is 3 rpm. 21s between articles
        # keeps us safely under that. when you add a payment method
        # later (3 rpm -> 300 rpm), drop this to 1s or remove entirely.
        if i < len(CORPUS):
            log.info("    sleeping 21s to respect voyage rate limit...")
            await asyncio.sleep(21)

    log.info("=== done ===")
    log.info("ingested: %d  skipped: %d  failed: %d", n_ingested, n_skipped, n_failed)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))