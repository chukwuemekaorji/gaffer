"""metrics for the eval runner.

we compute three classes of metric:

retrieval (configs 1-5):
  - recall@k: did relevant chunks appear in the top-k?
  - mrr: reciprocal rank of the first relevant chunk

answer quality (config 5 only — needs generated text):
  - route_match: did the router pick at least one expected route?
  - source_kind_match: did the answer cite at least one of each expected kind?
  - refusal_correctness: did refusal happen iff it should have?
  - faithfulness (llm-as-judge): did the answer make claims unsupported by retrieved evidence?

retrieval metrics use lexical overlap between candidate content and
the reference notes as a cheap proxy for relevance. it's not perfect —
a chunk could be relevant without sharing words — but it gives us
consistent comparison signal across configs without manual labelling.
the alternative is hand-labelling relevance per (query, chunk) pair,
which is good for production but overkill for a portfolio project."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.evals.dataset import EvalQuery
from app.retrieval.schemas import Candidate

log = logging.getLogger(__name__)


JUDGE_MODEL = "claude-haiku-4-5"


def _tokenise(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - _STOPWORDS


_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at",
    "for", "with", "from", "by", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "could", "this", "that", "these", "those", "it", "its", "as", "if",
}


def _content_overlap(candidate_content: str, reference: str) -> float:
    """jaccard overlap of significant tokens between a candidate chunk
    and the reference notes. used as a cheap relevance proxy."""
    a = _tokenise(candidate_content)
    b = _tokenise(reference)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# threshold above which we consider a chunk 'relevant' to the reference.
# tuned empirically — too low and everything counts, too high and
# nothing does. 0.06 catches articles that share several content words
# without requiring near-duplication.
RELEVANCE_THRESHOLD = 0.06


@dataclass
class RetrievalMetrics:
    recall_at_5: float
    mrr: float
    n_relevant_retrieved: int


def compute_retrieval_metrics(
    candidates: list[Candidate],
    query: EvalQuery,
    *,
    k: int = 5,
) -> RetrievalMetrics:
    """recall@k and mrr against the reference notes. for out-of-scope
    queries we treat zero retrieval as correct (recall = 1.0)."""

    if query.allow_refuse:
        # for refusal targets, we 'want' zero matches — perfect retrieval
        # means the agent had nothing relevant, prompting the refusal.
        n_irrelevant = sum(
            1 for c in candidates[:k]
            if _content_overlap(c.content, query.query) < RELEVANCE_THRESHOLD
        )
        recall = 1.0 if not candidates else n_irrelevant / max(len(candidates[:k]), 1)
        return RetrievalMetrics(recall_at_5=recall, mrr=0.0, n_relevant_retrieved=0)

    if not query.reference:
        return RetrievalMetrics(recall_at_5=0.0, mrr=0.0, n_relevant_retrieved=0)

    relevant_flags = [
        _content_overlap(c.content, query.reference) >= RELEVANCE_THRESHOLD
        for c in candidates[:k]
    ]
    n_relevant = sum(relevant_flags)

    # recall@k as 'at least one relevant in the top k' — binary signal,
    # the standard formulation for sparse single-document relevance.
    recall = 1.0 if n_relevant > 0 else 0.0

    # mrr: 1/rank of the first relevant chunk
    mrr = 0.0
    for rank, is_rel in enumerate(relevant_flags, start=1):
        if is_rel:
            mrr = 1.0 / rank
            break

    return RetrievalMetrics(
        recall_at_5=recall, mrr=mrr, n_relevant_retrieved=n_relevant
    )


@dataclass
class AnswerMetrics:
    route_match: bool
    source_kind_match: bool
    refusal_correct: bool
    faithfulness: float | None     # 0..1, None when we skipped the judge


def evaluate_route(query: EvalQuery, actual_routes: list[str] | None) -> bool:
    """route_match: at least one expected route appears in what the
    router actually picked."""
    if actual_routes is None:
        return False
    return any(r in actual_routes for r in query.expected_routes)


def evaluate_source_kinds(query: EvalQuery, actual_kinds: list[str] | None) -> bool:
    """source_kind_match: every expected kind has at least one source
    of that kind in the response."""
    if not query.expected_source_kinds:
        return True  # nothing to check
    if not actual_kinds:
        return False
    return all(k in actual_kinds for k in query.expected_source_kinds)


def evaluate_refusal(query: EvalQuery, actual_routes: list[str] | None) -> bool:
    refused = actual_routes is not None and "refuse" in actual_routes
    if query.allow_refuse:
        return refused
    return not refused


_judge_client: AsyncAnthropic | None = None


def _get_judge() -> AsyncAnthropic | None:
    global _judge_client
    if _judge_client is not None:
        return _judge_client
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    _judge_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _judge_client


FAITHFULNESS_PROMPT = """you are evaluating whether an answer is faithful to the evidence it was given.

input:
- a user question
- the evidence the agent retrieved (article snippets and structured facts)
- the answer the agent produced

your job: identify whether any claim in the answer is NOT supported by the evidence.

output strictly a json object: {"score": <float 0..1>, "unsupported_claims": [<string>, ...]}

score scale:
- 1.0: every claim in the answer is supported by the evidence
- 0.7: minor unsupported additions (e.g. cosmetic phrasing not tied to evidence)
- 0.4: at least one substantive unsupported claim
- 0.0: most of the answer is not supported by the evidence

if the agent refused, score is 1.0 (a refusal makes no factual claims).
do not output anything outside the json. no preamble. no markdown fences.
"""


async def judge_faithfulness(
    query: str,
    evidence_summary: str,
    answer: str,
) -> float | None:
    """llm-as-judge faithfulness score. returns None if the judge call
    fails — we skip this metric for that row rather than fail the run."""
    client = _get_judge()
    if client is None:
        return None

    user_message = (
        f"QUESTION: {query}\n\n"
        f"EVIDENCE:\n{evidence_summary or '(no evidence retrieved)'}\n\n"
        f"ANSWER:\n{answer}"
    )

    try:
        import json
        response = await client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=500,
            system=FAITHFULNESS_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            temperature=0.0,
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        parsed = json.loads(raw)
        return float(parsed.get("score", 0.0))
    except Exception as exc:
        log.warning("faithfulness judge failed: %s", exc)
        return None