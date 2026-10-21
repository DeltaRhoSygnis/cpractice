"""Phase 7.3 proof: a batch-prepared pset passes the gate end to end.

The live-provider variant of this proof is currently blocked: the Kenari
account returns HTTP 402 ("insufficient balance: available Rp 0"). The
*model* is therefore the one and only substituted part -- everything else
(the HTTP boundary, the shelf runner, the real GenerationPipeline, the real
QualityGate, the compiler, the runner, the comparator, the writer) is the
production code path, exercised over HTTP.

The proof asserts the spec's central property: a batch item is accepted only
if it survives the *same* deterministic gate as an interactive generation.

Usage:
    python3 phase7_batch_proof.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Run from anywhere: the repo root must be importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.ai.mock import MockBatchProvider
from app.config import Settings
from app.generation.batch import ShelfItem, ShelfRunner
from app.generation.pipeline import GenerationPipeline
from app.generation.prompts import GenerationRequest
from app.main import create_app
from app.schemas.problem import ProblemKind
from app.storage.problem_repository import ProblemRepository
from tests.test_pset_generation import pset_payload

FAILURES: list[str] = []


def step(label: str, ok: bool, detail: str = "") -> None:
    if not ok:
        FAILURES.append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


tmp = Path(tempfile.mkdtemp(prefix="cpractice-phase7-"))
problems_dir = tmp / "problems"

print(f"Phase 7.3 batch proof (model mocked; live provider is out of credit)\n")

# --- build a genuine, gate-passing pset payload ----------------------------
def pset_payload_for(problem_id: str, title: str) -> str:
    payload = pset_payload()
    payload["id"] = problem_id
    payload["title"] = title
    return json.dumps(payload)


IDS = ["shelf-alpha", "shelf-beta", "shelf-gamma"]
responses = {
    f"item-{index:03d}": pset_payload_for(pid, f"Shelf Pset {index}")
    for index, pid in enumerate(IDS)
}

provider = MockBatchProvider(batch_responses=responses)

settings = Settings(
    database_path=tmp / "data" / "cpractice.db",
    problems_dir=problems_dir,
    workspaces_dir=tmp / "workspaces",
    kenari_api_key=None,
    google_api_key=None,
)

app = create_app(settings)
with TestClient(app) as client:
    # The pipeline and the batch transport share one provider, exactly as in
    # production: the batch path must not get a different pipeline.
    pipeline = GenerationPipeline(
        provider,
        problems_dir=problems_dir,
        known_concepts=["for_loops", "input_output"],
    )
    app.state.generation_pipeline = pipeline
    app.state.batch_provider = provider

    # Declare the learner's checklist so concept legality is decidable.
    checklist = client.put(
        "/api/preferences/known-concepts",
        json={"known_concepts": ["for_loops", "input_output"]},
    )
    step("learner checklist declared", checklist.status_code == 200,
         f"status={checklist.status_code}")

    # --- the batch call, over HTTP ---------------------------------------
    response = client.post(
        "/api/problems/batch",
        json={
            "job_id": "phase7-proof",
            "items": [
                {
                    "custom_id": f"item-{index:03d}",
                    "topic": f"warehouse pallet tally {index}",
                    "kind": "problem_set",
                    "new_concept": "arrays",
                    "assumed_known": ["for_loops", "input_output"],
                }
                for index in range(3)
            ],
        },
    )
    status = response.status_code
    report = response.json()
    step("batch endpoint accepted the shelf", status == 200, f"status={status}")
    step("the shelf went out as ONE provider submission",
          len(provider.batch_calls) == 1, f"calls={len(provider.batch_calls)}")
    step("all three items went in that one submission",
          len(provider.batch_calls[0]) == 3, f"items={len(provider.batch_calls[0])}")

    items = report.get("items", [])
    step("three outcomes reported", len(items) == 3, f"items={len(items)}")
    validated = [i for i in items if i.get("outcome") == "validated"]
    step("all three items passed the gate", len(validated) == 3,
         f"outcomes={[i.get('outcome') for i in items]}")
    step("the report names the problems it produced",
         {i.get("problem_id") for i in validated} == set(IDS),
         f"ids={sorted(i.get('problem_id') or '' for i in validated)}")

    # --- the packages are real, on disk, and load back --------------------
    repository = ProblemRepository(problems_dir)
    for pid in IDS:
        package = problems_dir / pid
        step(f"{pid}: package written to disk", package.is_dir())
        if not package.is_dir():
            continue
        problem = repository.load(pid)
        step(f"{pid}: kind is problem_set",
             problem.metadata.kind is ProblemKind.PROBLEM_SET)
        step(f"{pid}: carries a concept pair",
             problem.metadata.concept is not None,
             str(problem.metadata.concept))
        step(f"{pid}: ships distribution code with TODOs",
             "TODO" in problem.starter_code,
             f"TODOs={problem.starter_code.count('TODO')}")
        step(f"{pid}: has a stored checker",
             problem.metadata.checker is not None,
             f"prefix={getattr(problem.metadata.checker, 'prefix', None)}")
        step(f"{pid}: has stored hints", len(problem.hints) > 0,
             f"{len(problem.hints)} hints")

    # --- and the gate is still the gate: a bad item is rejected -----------
    from app.generation.batch import ShelfRunner as _SR  # noqa: F401
    from app.ai.base import BatchRequest, BatchItemResult  # noqa: F401

    print()
    print("  -- proving the batch path cannot lower the bar --")
    bad_provider = MockBatchProvider(
        batch_responses={
            "item-000": "this is not JSON at all",
        }
    )
    bad_pipeline = GenerationPipeline(
        bad_provider,
        problems_dir=problems_dir,
        known_concepts=["for_loops", "input_output"],
    )
    runner = ShelfRunner(
        pipeline=bad_pipeline,
        batch_provider=bad_provider,
        problems_dir=problems_dir,
        known_concepts=["for_loops", "input_output"],
    )
    bad_report = runner.prepare(
        [
            ShelfItem(
                custom_id="item-000",
                request=GenerationRequest(
                    topic="malformed",
                    kind=ProblemKind.PROBLEM_SET,
                    new_concept="arrays",
                    assumed_known=["for_loops", "input_output"],
                ),
            )
        ],
        job_id="phase7-proof-bad",
    )
    step("a malformed batch item is REJECTED, not accepted",
         bad_report.items[0].outcome.value == "rejected",
         f"outcome={bad_report.items[0].outcome.value}")
    step("the rejection carries a finding",
         bool(bad_report.items[0].findings),
         str(bad_report.items[0].findings)[:120])

print()
if FAILURES:
    print(f"PROOF FAILED — {len(FAILURES)} check(s) failed: {FAILURES}")
    raise SystemExit(1)
print("PROOF PASSED — a batch-prepared pset passes the same gate end to end.")
