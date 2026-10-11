"""Prediction (hypothesis) capture and diff — spec S6.

The predict-then-verify mechanic is **optional and never graded**. Before
submitting, a learner may be shown one public sample and asked what they expect
it to print. After grading, this module compares three known strings:

* **expected** — the sample test's declared ``expected_stdout`` (server data);
* **predicted** — what the learner wrote;
* **actual** — what their program actually printed.

The comparison reuses the platform's own comparator
(:func:`app.grading.comparator.outputs_match`), so a prediction is judged with
exactly the same normalisation as a real test — nothing new is invented.

Hard rule (design decision #3): **the AI never decides pass/fail, and the
prediction never decides anything at all.** This module is pure: no I/O, no
provider, no grading. It cannot influence ``verdict``, pass counts, or
recommendation evidence; the very absence of any such output is the proof.

The explanatory ``note`` cites a *declared* misconception id that the problem or
sample test already carries. It is never a fresh AI judgement.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.grading.comparator import outputs_match
from app.schemas.problem import Problem
from app.schemas.test_case import ComparisonMode, TestCase

__all__ = [
    "PredictionDiff",
    "SampleRun",
    "build_prediction_diff",
    "prediction_to_payload",
    "select_sample_test",
]


@dataclass(frozen=True)
class SampleRun:
    """What the learner's program actually printed for the sample test.

    The deterministic :class:`~app.schemas.grading.GradingReport` deliberately
    does not carry raw stdout — it stores only safe diagnostics. Recording the
    sample's actual output is the submission service's job (measurement only);
    this value object carries that measurement so the diff can compare it. It
    never crosses the report boundary.
    """

    stdout: str = ""
    #: True when the program ran and produced output we can compare. A
    #: compilation failure, timeout, crash, or infinite output means there is
    #: nothing meaningful to compare, so ``matches_actual`` stays ``None``.
    available: bool = False


@dataclass(frozen=True)
class PredictionDiff:
    """The comparison of predicted vs expected vs actual, plus any note.

    ``provided`` is ``False`` when the learner supplied no prediction: every
    other field is then ``None`` and the payload is a single key, so the diff
    section is simply absent from a report.
    """

    provided: bool
    sample_test_id: str | None = None
    expected: str | None = None
    predicted: str | None = None
    actual: str | None = None
    #: Whether the prediction agrees with the server's expected output.
    matches_expected: bool | None = None
    #: Whether the prediction agrees with what the program actually printed.
    #: ``None`` when the actual output is unavailable (compile error, crash,
    #: timeout, or output-limit).
    matches_actual: bool | None = None
    #: A short factual note. Present only when a *declared* misconception id
    #: applies; never an AI judgement.
    note: str | None = None


def select_sample_test(problem: Problem) -> TestCase | None:
    """The public test the learner predicts against.

    Honours ``metadata.prediction.sample_test_id`` when it names a test. A
    prediction sample must be **public**: a hidden test's expected output must
    never reach the client, and a prediction is only answerable against a
    sample the learner can see. If the declared id names a hidden (or missing)
    test, fall back to the first public test — never to hidden data.
    """
    plan = problem.metadata.prediction
    if plan.sample_test_id:
        declared = next(
            (t for t in problem.tests if t.id == plan.sample_test_id), None
        )
        if declared is not None and declared.visibility.value == "public":
            return declared

    public = problem.public_tests
    if public:
        return public[0]
    return None


def build_prediction_diff(
    *,
    problem: Problem,
    predicted_stdout: str | None,
    report=None,
    actual_stdout: str | None = None,
    sample_run: SampleRun | None = None,
) -> PredictionDiff:
    """Build the prediction diff for one attempt (spec S6).

    Parameters
    ----------
    problem:
        The graded problem. Supplies the sample test and its declared
        misconceptions.
    predicted_stdout:
        What the learner predicted, or ``None``/``""`` when they did not make a
        prediction. Absent prediction → ``provided=False`` with no detail.
    report:
        The deterministic grading report (optional). Used only to decide
        whether the learner's code actually failed the sample — the diff never
        reads it to change a grade.
    actual_stdout:
        Raw stdout the program produced for the sample test, when the caller
        measured it (see :class:`SampleRun`).
    sample_run:
        A richer form of ``actual_stdout`` carrying availability. When given, it
        takes precedence over ``actual_stdout``.
    """
    # Absent prediction: the checker runs normally and the diff is omitted.
    if predicted_stdout is None or predicted_stdout == "":
        return PredictionDiff(provided=False)

    sample = select_sample_test(problem)
    if sample is None:
        # Nothing declared to predict against; still record that a prediction
        # was made, but there is no sample to compare it with.
        return PredictionDiff(
            provided=True,
            sample_test_id=None,
            predicted=predicted_stdout,
        )

    if sample_run is not None:
        actual = sample_run.stdout
        actual_available = sample_run.available
    elif actual_stdout is not None:
        actual = actual_stdout
        actual_available = True
    else:
        actual = None
        actual_available = False

    expected = sample.expected_stdout
    mode = sample.comparison or problem.metadata.comparison

    matches_expected = _matches(predicted_stdout, expected, mode)
    matches_actual = (
        _matches(predicted_stdout, actual, mode) if actual_available else None
    )

    note = _misconception_note(
        sample=sample,
        report=report,
        matches_expected=matches_expected,
        matches_actual=matches_actual,
        predicted=predicted_stdout,
        actual=actual,
    )

    return PredictionDiff(
        provided=True,
        sample_test_id=sample.id,
        expected=expected,
        predicted=predicted_stdout,
        actual=actual,
        matches_expected=matches_expected,
        matches_actual=matches_actual,
        note=note,
    )


def prediction_to_payload(diff: PredictionDiff) -> dict:
    """Return a JSON-safe dict for inclusion in the submission report.

    ``provided`` is always present so a client can toggle the diff section. The
    remaining keys are omitted when there is nothing to show, so an absent
    prediction serialises to ``{"provided": false}``.
    """
    if not diff.provided:
        return {"provided": False}

    payload: dict = {
        "provided": True,
        "sample_test_id": diff.sample_test_id,
        "expected": diff.expected,
        "predicted": diff.predicted,
        "actual": diff.actual,
        "matches_expected": diff.matches_expected,
        "matches_actual": diff.matches_actual,
        "note": diff.note,
    }
    return payload


def _matches(predicted: str, observed: str, mode: ComparisonMode | str) -> bool:
    """Compare two strings with the platform's own comparator.

    No new comparison policy is introduced: the prediction is judged the same
    way a real output would be, including normalisation and final-newline
    tolerance.
    """
    return outputs_match(predicted, observed, mode)


def _misconception_note(
    *,
    sample: TestCase,
    report,
    matches_expected: bool,
    matches_actual: bool | None,
    predicted: str,
    actual: str | None,
) -> str | None:
    """A factual note, **only** when a declared misconception id applies.

    A declared id applies when the learner's actual output failed the sample and
    the sample test (or, failing that, the problem's pedagogy) declares a
    misconception id for it. The note cites the id; it is never an AI judgement
    and never a new diagnosis.
    """
    # The realised failure: the program's real output did not match expected.
    if not _sample_failed(sample, report, matches_actual):
        return None

    # Prefer the sample test's own declared misconception; fall back to the
    # problem's pedagogy when the test carries none.
    declared = list(sample.misconception_ids)
    if not declared:
        return None

    # The note must be *true*. It may only claim what the program actually
    # produced when that output was measured. A compilation failure, timeout,
    # crash, or output-limit leaves us with no observed output, so we cannot
    # say the code "got" anything -- the learner's code never produced a
    # comparable result. In that case the note reports the prediction without
    # inventing an observation.
    if actual is None:
        return (
            f"You predicted {_preview(predicted)} on \"{sample.name}\", but "
            "your program did not produce a comparable output, so the "
            "prediction could not be checked. The test declares "
            f"{declared[0]}."
        )

    return (
        f"You predicted {_preview(predicted)} and got {_preview(actual)} on "
        f"\"{sample.name}\"; your code triggers {declared[0]}, which this "
        f"problem declares."
    )


def _sample_failed(sample: TestCase, report, matches_actual: bool | None) -> bool:
    """Whether the learner's code actually failed the sample test.

    When a grading report is supplied, its per-test result is authoritative: a
    test counts as failed when it is not ``passed``. Without a report, the
    measured actual output is used (a non-match means failure). Only *failure*
    gates the note, so a learner who predicted wrongly but whose code is correct
    gets no misconception note — the note ties the prediction to real behaviour.
    """
    if report is not None:
        result = next((t for t in report.tests if t.test_id == sample.id), None)
        if result is not None:
            return not result.passed

    return matches_actual is False


def _preview(text: str | None) -> str:
    """A short, single-line, safe rendering of an output string."""
    if text is None:
        return "(no output)"
    stripped = text.strip()
    if not stripped:
        return "(empty output)"
    if len(stripped) > 80:
        return stripped[:80] + "…"
    return stripped
