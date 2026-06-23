"""orchestrates extract -> chunk -> embed -> persist for a single url.
this is the function every ingestion path eventually calls — manual cli,
rss poller, post-match job. keeping it as one function with a clear
signature means callers can't accidentally skip a step."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.ingestion import repository
from app.ingestion.chunker import chunk_text
from app.ingestion.embedder import embed_texts
from app.ingestion.extractor import ExtractedDocument, extract, fetch_html
from app.ingestion.repository import ChunkMetadata

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    document_id: int | None
    chunks_inserted: int
    skipped: bool
    reason: str | None = None


async def ingest_url(
    db: Session,
    *,
    url: str,
    source: str,
    doc_type: str,
    metadata: ChunkMetadata | None = None,
) -> IngestResult:
    """fetches a url, extracts content, chunks it, embeds the chunks,
    and writes everything to postgres. idempotent on url — re-running
    against an already-ingested url is a no-op (returns skipped=true)."""

    metadata = metadata or ChunkMetadata()

    # 1. dedup. cheapest check we can do — bail before any network work
    # on the embeddings api.
    existing = repository.find_document_by_url(db, url)
    if existing is not None:
        return IngestResult(document_id=existing, chunks_inserted=0, skipped=True, reason="duplicate_url")

    # 2. fetch + extract
    html = await fetch_html(url)
    if html is None:
        return IngestResult(document_id=None, chunks_inserted=0, skipped=True, reason="fetch_failed")

    extracted = extract(html, url=url, source=source)
    if extracted is None:
        return IngestResult(document_id=None, chunks_inserted=0, skipped=True, reason="extraction_failed")

    # 3. chunk + embed
    chunks = chunk_text(extracted.content)
    if not chunks:
        return IngestResult(document_id=None, chunks_inserted=0, skipped=True, reason="no_chunks")

    embeddings = await embed_texts([c.content for c in chunks], input_type="document")

    # 4. persist. one transaction for document + all chunks so a partial
    # failure doesn't leave orphan documents behind.
    document_id = repository.insert_document(db, extracted, doc_type=doc_type)
    inserted = repository.insert_chunks(
        db,
        document_id=document_id,
        chunks=chunks,
        embeddings=embeddings,
        metadata=metadata,
        published_at=extracted.published_at,
    )
    db.commit()
    log.info("ingested url=%s chunks=%d", url, inserted)

    return IngestResult(document_id=document_id, chunks_inserted=inserted, skipped=False)


async def ingest_raw_text(
    db: Session,
    *,
    title: str,
    content: str,
    source: str,
    doc_type: str,
    url: str | None = None,
    published_at: datetime | None = None,
    metadata: ChunkMetadata | None = None,
) -> IngestResult:
    """same pipeline but for content we already have in hand — e.g. a
    curated tactical primer pasted from a pdf or written from scratch.
    no fetching, no extraction, straight into chunking."""

    metadata = metadata or ChunkMetadata()

    # use a synthetic url so the dedup check still works for repeated runs
    effective_url = url or f"internal://{source}/{title}"
    existing = repository.find_document_by_url(db, effective_url)
    if existing is not None:
        return IngestResult(document_id=existing, chunks_inserted=0, skipped=True, reason="duplicate_url")

    extracted = ExtractedDocument(
        url=effective_url,
        title=title,
        content=content,
        published_at=published_at,
        author=None,
        source=source,
    )

    chunks = chunk_text(content)
    if not chunks:
        return IngestResult(document_id=None, chunks_inserted=0, skipped=True, reason="no_chunks")

    embeddings = await embed_texts([c.content for c in chunks], input_type="document")

    document_id = repository.insert_document(db, extracted, doc_type=doc_type)
    inserted = repository.insert_chunks(
        db,
        document_id=document_id,
        chunks=chunks,
        embeddings=embeddings,
        metadata=metadata,
        published_at=published_at,
    )
    db.commit()
    log.info("ingested raw text title=%s chunks=%d", title, inserted)

    return IngestResult(document_id=document_id, chunks_inserted=inserted, skipped=False)