"""reciprocal rank fusion — combines ranked lists from semantic and
lexical retrieval into a single ranking.

rrf is the right fusion choice when component scores aren't directly
comparable. semantic scores are cosine similarities (0..1, calibrated);
bm25 scores are unbounded and depend on corpus statistics. you can't
just add them. but rank position is comparable across both — rank 1 is
rank 1 regardless of where the score came from.

formula per item: rrf_score = sum_over_lists(1 / (k + rank))
where k = 60 (the convention from the original paper). higher rank
positions contribute more, with diminishing returns. items appearing
high in both lists get the biggest boost."""

from __future__ import annotations

from collections.abc import Iterable

from app.retrieval.schemas import Candidate

RRF_K = 60


def fuse_candidates(
    *candidate_lists: Iterable[Candidate],
    limit: int = 30,
) -> list[Candidate]:
    """merges any number of ranked candidate lists into a single list
    ranked by rrf score. preserves the per-stage scores so downstream
    code can inspect them."""

    # collect candidates by chunk_id so we can merge per-stage scores
    merged: dict[int, Candidate] = {}

    for candidate_list in candidate_lists:
        candidates = list(candidate_list)
        for rank, c in enumerate(candidates, start=1):
            existing = merged.get(c.chunk_id)
            rrf_contribution = 1.0 / (RRF_K + rank)

            if existing is None:
                # first time we've seen this chunk — copy it and start
                # its rrf accumulator
                c.rrf_score = rrf_contribution
                merged[c.chunk_id] = c
            else:
                # already seen — merge any new per-stage scores and add
                # to the rrf accumulator
                existing.rrf_score = (existing.rrf_score or 0.0) + rrf_contribution
                if c.semantic_score is not None and existing.semantic_score is None:
                    existing.semantic_score = c.semantic_score
                if c.lexical_score is not None and existing.lexical_score is None:
                    existing.lexical_score = c.lexical_score

    fused = sorted(merged.values(), key=lambda c: c.rrf_score or 0.0, reverse=True)
    return fused[:limit]