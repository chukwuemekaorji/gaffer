"""one-shot eval runner.

usage:
    python -m scripts.run_evals
    python -m scripts.run_evals --no-judge   # skip the faithfulness llm
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.evals.runner import run_evals

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="run the gaffer eval set across all configurations")
    p.add_argument(
        "--no-judge",
        action="store_true",
        help="skip the llm-as-judge faithfulness scoring (faster + cheaper)",
    )
    p.add_argument(
        "--out",
        default="evals/results.csv",
        help="csv output path (relative to backend/)",
    )
    return p.parse_args()


async def main() -> int:
    args = parse_args()
    out_path = Path(args.out)
    await run_evals(
        judge_faithfulness_for_full=not args.no_judge,
        output_csv=out_path,
    )
    print(f"\nresults written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))