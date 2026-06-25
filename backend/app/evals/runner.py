"""runs the eval set across all configurations and writes a results
csv plus a summary table to stdout.

the runner is intentionally synchronous-shaped at the top level
(`asyncio.run`) so we can invoke it from a one-line script. inside,
queries run concurrently per config — voyage and cohere both batch well."""

from __future__ import annotations

import asyncio
import csv
import logging
import statistics
import time
from collections.abc import Awaitable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.evals.configurations import CONFIGURATIONS, ConfigResult
from app.evals.dataset import DATASET, EvalQuery
from app.evals.metrics import (
    AnswerMetrics,
    compute_retrieval_metrics,
    evaluate_refusal,
    evaluate_route,
    evaluate_source_kinds,
    judge_faithfulness,
)

log = logging.getLogger(__name__)


@dataclass
class RowResult:
    config: str
    query_id: str
    category: str
    query: str
    recall_at_5: float
    mrr: float
    n_relevant: int
    route_match: bool | None
    source_kind_match: bool | None
    refusal_correct: bool | None
    faithfulness: float | None
    latency_ms: int


async def _evaluate_one(
    config_name: str,
    config_fn: Any,
    query: EvalQuery,
    db: Session,
    *,
    judge_faithfulness_for_full: bool,
) -> RowResult:
    started = time.perf_counter()
    try:
        result: ConfigResult = await config_fn(db, query.query)
    except Exception as exc:
        log.warning("config=%s query=%s failed: %s", config_name, query.id, exc)
        elapsed = int((time.perf_counter() - started) * 1000)
        return RowResult(
            config=config_name,
            query_id=query.id,
            category=query.category,
            query=query.query,
            recall_at_5=0.0,
            mrr=0.0,
            n_relevant=0,
            route_match=None,
            source_kind_match=None,
            refusal_correct=None,
            faithfulness=None,
            latency_ms=elapsed,
        )


    elapsed_ms = int((time.perf_counter() - started) * 1000)

    retrieval = compute_retrieval_metrics(result.candidates, query)

    route_match: bool | None = None
    source_kind_match: bool | None = None
    refusal_correct: bool | None = None
    faithfulness: float | None = None

    if config_name == "5_full":
        route_match = evaluate_route(query, result.decision_routes)
        source_kind_match = evaluate_source_kinds(query, result.cited_source_kinds)
        refusal_correct = evaluate_refusal(query, result.decision_routes)

        if judge_faithfulness_for_full and result.answer:
            evidence_summary = "\n".join(
                f"- {c.title}: {c.content[:280]}"
                for c in result.candidates[:5]
            )
            faithfulness = await judge_faithfulness(query.query, evidence_summary, result.answer)

    return RowResult(
        config=config_name,
        query_id=query.id,
        category=query.category,
        query=query.query,
        recall_at_5=retrieval.recall_at_5,
        mrr=retrieval.mrr,
        n_relevant=retrieval.n_relevant_retrieved,
        route_match=route_match,
        source_kind_match=source_kind_match,
        refusal_correct=refusal_correct,
        faithfulness=faithfulness,
        latency_ms=elapsed_ms,
    )


async def run_evals(
    *,
    judge_faithfulness_for_full: bool = True,
    output_csv: Path | None = None,
) -> list[RowResult]:
    """runs every config against the full dataset. returns a flat list
    of row results, also writes a csv if a path is given."""
    rows: list[RowResult] = []

    for config_name, config_fn in CONFIGURATIONS.items():
        log.info("=== config=%s ===", config_name)
        # new session per config so transactional context is clean
        db = SessionLocal()
        try:
            tasks: list[Awaitable[RowResult]] = [
                _evaluate_one(
                    config_name, config_fn, q, db,
                    judge_faithfulness_for_full=judge_faithfulness_for_full,
                )
                for q in DATASET
            ]
            # bounded concurrency — voyage and cohere are tolerant but
            # we don't want to fire 40 simultaneous requests.
            semaphore = asyncio.Semaphore(1)

            async def gated(task: Awaitable[RowResult]) -> RowResult:
                async with semaphore:
                    result = await task
                    await asyncio.sleep(21)  # ~3 requests per minute headroom
                    return result

            config_rows = await asyncio.gather(*[gated(t) for t in tasks])
            rows.extend(config_rows)
        finally:
            db.close()

    if output_csv is not None:
        write_csv(rows, output_csv)

    print_summary(rows)
    return rows


def write_csv(rows: list[RowResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def _mean(values: list[float]) -> float:
    nonnull = [v for v in values if v is not None]
    return statistics.mean(nonnull) if nonnull else 0.0


def _pct(values: list[bool | None]) -> float:
    nonnull = [v for v in values if v is not None]
    if not nonnull:
        return 0.0
    return sum(1 for v in nonnull if v) / len(nonnull)


def print_summary(rows: list[RowResult]) -> None:
    """prints the headline comparison table to stdout. this is the
    table that ends up in the README."""

    by_config: dict[str, list[RowResult]] = {}
    for row in rows:
        by_config.setdefault(row.config, []).append(row)

    print("\n" + "=" * 90)
    print(f"{'Config':<14} {'Recall@5':>9} {'MRR':>7} {'RouteMatch':>11} {'KindMatch':>10} {'Refusal':>8} {'Faith':>7} {'Avg ms':>8}")
    print("-" * 90)

    for config_name in CONFIGURATIONS.keys():
        config_rows = by_config.get(config_name, [])
        if not config_rows:
            continue
        recall = _mean([r.recall_at_5 for r in config_rows])
        mrr = _mean([r.mrr for r in config_rows])
        route_match = _pct([r.route_match for r in config_rows])
        kind_match = _pct([r.source_kind_match for r in config_rows])
        refusal = _pct([r.refusal_correct for r in config_rows])
        faith = _mean([r.faithfulness for r in config_rows if r.faithfulness is not None])
        latency = _mean([r.latency_ms for r in config_rows])

        print(
            f"{config_name:<14} {recall:>9.3f} {mrr:>7.3f} "
            f"{route_match:>11.2f} {kind_match:>10.2f} {refusal:>8.2f} "
            f"{faith:>7.3f} {latency:>8.0f}"
        )
    print("=" * 90)
    print(f"\nTotal queries: {len(DATASET)}")
    print(f"Total rows: {len(rows)}\n")