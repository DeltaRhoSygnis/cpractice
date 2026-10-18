"""Command-line entry point for shelf preparation (spec S7).

Prepares a shelf of problem sets in one Gemini Batch run and prints the
per-item report. Intended to be run ahead of a session, so the learner opens a
ready pset and works offline from the provider::

    python -m app.generation.batch_cli \
        --new-concept arrays --assumed-known for_loops,input_output \
        --topic voting --items 3

The runner it drives is exactly the one the HTTP endpoint uses: the same
:class:`~app.generation.pipeline.GenerationPipeline`, the same
:class:`~app.generation.quality_gate.QualityGate`. The CLI only assembles
configuration and prints the result.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.ai.cache import GenerationCache
from app.ai.google_batch import GoogleBatchProvider
from app.config import Settings, get_settings
from app.generation.batch import ShelfItem, ShelfRunner
from app.generation.pipeline import GenerationPipeline
from app.generation.prompts import GenerationRequest
from app.schemas.problem import ProblemKind
from app.storage.database import Database
from app.storage.usage_ledger import BatchProvenanceStore, UsageLedger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.generation.batch_cli",
        description="Prepare a shelf of problem sets in one batch provider run.",
    )
    parser.add_argument("--topic", default="voting", help="subject area for the psets")
    parser.add_argument(
        "--difficulty",
        default="beginner",
        choices=["beginner", "intermediate", "advanced"],
    )
    parser.add_argument("--items", type=int, default=1, help="how many psets to prepare")
    parser.add_argument(
        "--new-concept", required=True, help="the one new concept each pset introduces"
    )
    parser.add_argument(
        "--assumed-known",
        default="",
        help="comma-separated concepts the learner already knows",
    )
    parser.add_argument("--known-concepts", default="", help="the stored checklist (comma-separated)")
    parser.add_argument("--job-id", default="", help="override the job id")
    return parser


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings: Settings = get_settings()

    provider = GoogleBatchProvider(settings.google_api_key, model=settings.ai_model)
    database = Database(settings.database_file)
    ledger = UsageLedger(database)
    provenance = BatchProvenanceStore(database)

    pipeline = GenerationPipeline(
        provider,
        problems_dir=settings.problems_path,
        cache=GenerationCache(settings.problems_path / ".cache"),
        known_concepts=_split(args.known_concepts),
    )

    assumed_known = _split(args.assumed_known)
    items = [
        ShelfItem(
            custom_id=f"cli-{index:03d}",
            request=GenerationRequest(
                topic=args.topic,
                difficulty=args.difficulty,
                kind=ProblemKind.PROBLEM_SET,
                new_concept=args.new_concept,
                assumed_known=assumed_known,
            ),
        )
        for index in range(max(1, args.items))
    ]

    runner = ShelfRunner(
        pipeline=pipeline,
        batch_provider=provider,
        problems_dir=settings.problems_path,
        provenance_store=provenance,
        daily_budget=settings.ai_daily_request_budget,
        requests_today=ledger.today().requests,
        known_concepts=_split(args.known_concepts),
    )

    job_id = args.job_id or f"cli-batch-{len(items)}"
    report = runner.prepare(items, job_id=job_id)

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0 if report.validated or report.cached else 1


if __name__ == "__main__":  # pragma: no cover - CLI wiring
    sys.exit(main())
