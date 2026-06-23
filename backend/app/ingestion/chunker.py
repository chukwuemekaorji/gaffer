"""splits long documents into retrieval-sized chunks. there are a few
schools of thought on chunking:
  - fixed-size by characters (simplest, can split mid-sentence)
  - fixed-size by tokens (closer to what embedding models care about)
  - recursive splitting (try paragraph, then sentence, then word)
  - semantic chunking (split on topic shifts via embeddings)

we're doing recursive paragraph-then-sentence splitting with token-based
size limits. it's the right balance: respects natural document structure,
hits the size we want, doesn't require a second llm call per chunk."""

from __future__ import annotations

import re
from dataclasses import dataclass

# voyage-3-large supports up to 32k tokens per input, but retrieval
# quality drops sharply with very large chunks (the embedding becomes
# a fuzzy average of too many ideas). 500 tokens with 80-token overlap
# is the conventional sweet spot for prose.
DEFAULT_CHUNK_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 80

# rough rule of thumb: 1 token ≈ 4 characters for english prose. we
# use this to avoid running a real tokeniser on every chunk — at this
# stage we just need a target size, not exact accounting. when we hand
# the chunks to voyage it does its own tokenisation.
CHARS_PER_TOKEN = 4


@dataclass
class Chunk:
    index: int          # position within the parent document
    content: str
    token_count: int    # estimated, not exact


def _split_paragraphs(text: str) -> list[str]:
    # paragraphs are the most semantically meaningful boundary in prose,
    # so we start here. two or more newlines = paragraph break.
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def _split_sentences(paragraph: str) -> list[str]:
    # very lightweight sentence splitter. we're not parsing legal docs;
    # for journalism this catches >95% of boundaries. if a sentence ends
    # in 'Dr.' or 'U.S.' we might over-split, but that's harmless for
    # retrieval — chunk boundaries don't have to be perfect.
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    return [s.strip() for s in sentences if s.strip()]


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def chunk_text(
    text: str,
    *,
    target_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    """returns a list of chunks, each roughly target_tokens long with
    overlap_tokens shared with the previous chunk. overlap matters
    because semantic context near chunk boundaries would otherwise be
    lost — a retrieved chunk needs some lead-in to be understandable."""

    target_chars = target_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    paragraphs = _split_paragraphs(text)
    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_len = 0

    def flush() -> None:
        nonlocal buffer, buffer_len
        if not buffer:
            return
        content = " ".join(buffer).strip()
        if content:
            chunks.append(
                Chunk(
                    index=len(chunks),
                    content=content,
                    token_count=_estimate_tokens(content),
                )
            )
        # build the overlap for the next chunk by walking backwards from
        # the end of the buffer until we hit the overlap budget.
        tail_chars = 0
        tail: list[str] = []
        for piece in reversed(buffer):
            if tail_chars + len(piece) > overlap_chars:
                break
            tail.insert(0, piece)
            tail_chars += len(piece)
        buffer = tail
        buffer_len = tail_chars

    for para in paragraphs:
        # if the paragraph alone is larger than the chunk budget, we have
        # to break it down further. fall through to sentence splitting.
        if len(para) > target_chars:
            for sent in _split_sentences(para):
                if buffer_len + len(sent) > target_chars and buffer:
                    flush()
                buffer.append(sent)
                buffer_len += len(sent) + 1
            continue

        # normal case: add the paragraph, flush if we've exceeded budget.
        if buffer_len + len(para) > target_chars and buffer:
            flush()
        buffer.append(para)
        buffer_len += len(para) + 2     # +2 accounts for the joining whitespace

    flush()
    return chunks