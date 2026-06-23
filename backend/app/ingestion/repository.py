"""writes documents and chunks to postgres. kept separate from the
pipeline so we can unit-test it in isolation later, and so the retrieval
layer can reuse the same database session helpers."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ingestion.chunker import Chunk
from app.ingestion.extractor import ExtractedDocument

log = logging.getLogger(__name__)


@dataclass
class ChunkMetadata:
    """metadata applied to every chunk of a given document. these are
    the filter dimensions the retrieval layer uses — see chunks table
    schema for full reasoning on the denormalised design."""

    era: str | None = None
    season: str | None = None
    topic: str | None = None
    players_mentioned: list[str] | None = None
    competition: str | None = None
    match_id: int | None = None


def _url_hash(url: str) -> str:
    # used for dedup. urls can have tracking params that change between
    # ingests of the same article, so we canonicalise to lowercase and
    # strip the fragment before hashing. could go further (strip utm_*
    # params, normalise trailing slashes) but this is good enough until
    # we see real duplicates slip through.
    cleaned = url.split("#")[0].strip().lower()
    return hashlib.sha256(cleaned.encode()).hexdigest()


def find_document_by_url(db: Session, url: str) -> int | None:
    """returns the document id if this url has already been ingested,
    else None. cheap check we run before any embedding work."""
    row = db.execute(
        text("select id from documents where url = :url limit 1"),
        {"url": url},
    ).first()
    return row[0] if row else None


def insert_document(
    db: Session,
    doc: ExtractedDocument,
    *,
    doc_type: str,
    extra: dict[str, Any] | None = None,
) -> int:
    """inserts a document row and returns its id. assumes caller has
    already checked for dedup with find_document_by_url."""
    result = db.execute(
        text(
            """
            insert into documents (url, title, source, doc_type, published_at, extra)
            values (:url, :title, :source, :doc_type, :published_at, cast(:extra as jsonb))
            returning id
            """
        ),
        {
            "url": doc.url,
            "title": doc.title,
            "source": doc.source,
            "doc_type": doc_type,
            "published_at": doc.published_at,
            "extra": _jsonb(extra or {"author": doc.author, "url_hash": _url_hash(doc.url)}),
        },
    )
    return result.scalar_one()


def insert_chunks(
    db: Session,
    *,
    document_id: int,
    chunks: list[Chunk],
    embeddings: list[list[float]],
    metadata: ChunkMetadata,
    published_at: datetime | None,
) -> int:
    """bulk-inserts chunks with their embeddings. expects len(chunks) ==
    len(embeddings); the pipeline guarantees that by embedding in the
    same order the chunker emits."""

    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunk/embedding count mismatch: {len(chunks)} vs {len(embeddings)}"
        )

    # build the parameter list for a single executemany insert. faster
    # than looping with one round-trip per chunk, and it lets postgres
    # plan the batch as one transaction.
    params = [
        {
            "document_id": document_id,
            "chunk_index": c.index,
            "content": c.content,
            "embedding": str(emb),         # pgvector accepts the python list rendered as a string
            "era": metadata.era,
            "season": metadata.season,
            "topic": metadata.topic,
            "players_mentioned": metadata.players_mentioned or [],
            "competition": metadata.competition,
            "match_id": metadata.match_id,
            "published_at": published_at,
            "token_count": c.token_count,
        }
        for c, emb in zip(chunks, embeddings)
    ]

    db.execute(
        text(
            """
            insert into chunks (
                document_id, chunk_index, content, embedding,
                era, season, topic, players_mentioned,
                competition, match_id, published_at, token_count
            )
            values (
                :document_id, :chunk_index, :content, cast(:embedding as vector),
                :era, :season, :topic, :players_mentioned,
                :competition, :match_id, :published_at, :token_count
            )
            """
        ),
        params,
    )
    return len(params)


def _jsonb(obj: dict[str, Any]) -> str:
    # sqlalchemy + psycopg + jsonb plays nicest when we pass a json string
    # and cast it server-side. avoids edge cases with nested dicts and
    # datetime serialisation.
    import json
    return json.dumps(obj, default=str)