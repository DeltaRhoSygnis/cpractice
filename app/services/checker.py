"""Generation-time checker metadata (spec S5).

The checker is an *ordered, named, dependency-aware presentation layer* over the
tests that already exist. It is never a new execution path: the runner,
compiler, comparator and evaluator are untouched. This module only:

* **builds** a deterministic :class:`CheckerPlan` from a problem (synthesising
  the ``exists`` and ``compiles`` prefix checks, then mapping each
  :class:`TestCase` to one behavioural check in declaration order), and
* **evaluates** that plan against a :class:`GradingReport`, reporting each check
  as passed, failed, or **blocked**.

The dependency rule (spec S5, S10):

* if ``exists`` fails, everything after it is **blocked**, not failed;
* if ``compiles`` fails, every behavioural check is **blocked** with cause
  ``compilation failed``.

A blocked check is not the learner's failure of that requirement - it simply
could not run yet, exactly as ``check50`` says *can't check until a frown turns
upside down*. Keeping the distinction honest keeps feedback truthful.

Determinism is a hard requirement: the same problem always yields the same plan,
and the same plan + report always yields the same results. No AI supplies order,
names, or dependencies.
"""

from __future__ import annotations

from app.schemas.grading import GradingReport
from app.schemas.problem import CheckSpec, CheckerPlan, Problem
from app.schemas.test_case import Visibility

#: The two synthesised prefix checks, in order. Never AI-authored (spec S5).
PREFIX_IDS: tuple[str, ...] = ("exists", "compiles")

#: Cause attached to a check that is blocked because a dependency failed.
BLOCKED_CAUSE_COMPILATION = "compilation failed"
BLOCKED_CAUSE_EXISTS = "submission not found"


def build_checker(problem: Problem) -> CheckerPlan:
    """Build the deterministic checker for ``problem`` (spec S5).

    Order is fixed: ``exists``, ``compiles``, then one behavioural check per
    test in the problem's declaration order. ``exists``/``compiles`` descriptions
    are derived from the entrypoint; behavioural descriptions reuse the test
    name so a checker is always presentable.
    """
    entrypoint = problem.metadata.entrypoint

    checks: list[CheckSpec] = [
        CheckSpec(
            id="exists",
            description=f"{entrypoint} exists.",
            after=None,
            visibility=Visibility.PUBLIC,
            test_id=None,
        ),
        CheckSpec(
            id="compiles",
            description=f"{entrypoint} compiles.",
            after="exists",
            visibility=Visibility.PUBLIC,
            test_id=None,
        ),
    ]

    for test in problem.tests:
        checks.append(
            CheckSpec(
                id=test.id,
                description=test.name,
                after="compiles",
                visibility=test.visibility,
                test_id=test.id,
            )
        )

    return CheckerPlan(prefix=list(PREFIX_IDS), checks=checks)


def evaluate_checks(
    plan: CheckerPlan,
    report: GradingReport,
    *,
    exists_passed: bool = True,
) -> list[dict]:
    """Evaluate ``plan`` against ``report`` into client-safe check results.

    Each result is ``{name, description, passed, blocked, cause, data,
    visibility}``. ``data`` is deliberately always empty here: the checker is a
    *status* view, and hidden tests must never expose stdin or expected stdout.

    ``exists_passed`` defaults to ``True``: the local submission path accepts
    source text, so a submission that reached the checker always exists (an
    empty submission is rejected earlier as a validation error). The flag exists
    so the dependency rule stays exercisable, and so a future file-based
    submission path can report a genuine miss without changing this module.
    """
    tests_by_id = {t.test_id: t for t in report.tests}
    compilation_ok = report.compilation.success

    results: list[dict] = []
    #: Ids whose outcome makes every dependent check *blocked* rather than
    #: failed. Seeded with ``exists`` when the submission did not arrive, and
    #: grown as ``compiles`` or a dependency itself blocks downstream checks.
    unresolved: set[str] = set()

    for spec in plan.checks:
        blocked = False
        passed = False
        cause: str | None = None

        if spec.id == "exists":
            passed = exists_passed
            if not passed:
                cause = BLOCKED_CAUSE_EXISTS
                unresolved.add(spec.id)
        else:
            # Anything after an unresolved dependency is blocked, not failed.
            dependency = spec.after
            if dependency is not None and dependency in unresolved:
                blocked = True
                passed = False
                cause = (
                    BLOCKED_CAUSE_EXISTS
                    if dependency == "exists"
                    else BLOCKED_CAUSE_COMPILATION
                )
                # A blocked check is unresolved for its own dependents too.
                unresolved.add(spec.id)
            elif spec.id in PREFIX_IDS:
                # ``compiles`` itself: passes iff the submission compiled.
                passed = compilation_ok
                if not passed:
                    cause = BLOCKED_CAUSE_COMPILATION
                    unresolved.add(spec.id)
            elif not compilation_ok:
                # Behavioural check whose (default ``compiles``) dependency
                # failed: blocked, not failed.
                blocked = True
                passed = False
                cause = BLOCKED_CAUSE_COMPILATION
                unresolved.add(spec.id)
            else:
                result = tests_by_id.get(spec.test_id) if spec.test_id else None
                passed = bool(result is not None and result.passed)
                if not passed:
                    cause = "did not pass"

        results.append(
            {
                "name": spec.id,
                "description": spec.description,
                "passed": passed,
                "blocked": blocked,
                "cause": cause,
                "data": {},
                "visibility": spec.visibility.value,
            }
        )

    return results


__all__ = [
    "BLOCKED_CAUSE_COMPILATION",
    "BLOCKED_CAUSE_EXISTS",
    "PREFIX_IDS",
    "build_checker",
    "evaluate_checks",
]
