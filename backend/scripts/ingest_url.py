"""one-shot url ingestion from the command line.

usage:
    python -m scripts.ingest_url https://www.example.com/article \\
        --source bbc_sport \\
        --doc-type news \\
        --era carrick \\
        --topic transitions

useful for:
  - seeding the curated tactical corpus a few articles at a time
  - debugging the pipeline against a known-good article
  - smoke-testing voyage / supabase wiring without scheduling anything
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.db.session import SessionLocal
from app.ingestion.pipeline import ingest_url
from app.ingestion.repository import ChunkMetadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ingest a single url into gaffer")
    p.add_argument("url")
    p.add_argument("--source", required=True, help="e.g. bbc_sport, the_athletic, manutd_official")
    p.add_argument("--doc-type", required=True, choices=["news", "match_report", "tactical_primer", "player_profile", "interview"])
    p.add_argument("--era", default=None, help="ten_hag | amorim | carrick")
    p.add_argument("--season", default=None, help="e.g. 2025-26")
    p.add_argument("--topic", default=None, help="pressing, transitions, set_pieces, etc")
    p.add_argument("--players", nargs="*", default=None, help="space-separated, e.g. mainoo bruno_fernandes")
    p.add_argument("--competition", default=None)
    return p.parse_args()


async def main() -> int:
    args = parse_args()
    metadata = ChunkMetadata(
        era=args.era,
        season=args.season,
        topic=args.topic,
        players_mentioned=args.players,
        competition=args.competition,
    )

    db = SessionLocal()
    try:
        result = await ingest_url(
            db,
            url=args.url,
            source=args.source,
            doc_type=args.doc_type,
            metadata=metadata,
        )
    finally:
        db.close()

    if result.skipped:
        print(f"skipped: {result.reason}")
        return 0 if result.reason == "duplicate_url" else 1

    print(f"ingested document_id={result.document_id} chunks={result.chunks_inserted}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))