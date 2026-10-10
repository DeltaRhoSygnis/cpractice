"""Tests for the progressive hint service."""

from __future__ import annotations

import pytest

from app.ai.mock import MockProvider
from app.feedback.hint_service import (
    SOLUTION_LEVEL,
    HintForbiddenError,
    HintService,
    HintUnavailableError,
)
from app.schemas.problem import Hint, Problem, ProblemMetadata


def _problem(*, hints: bool = True, reference: str = "int main(void){return 0;}") -> Problem:
    hint_list = [Hint(level=i, text=f"stored hint {i}") for i in range(1, 6)] if hints else []
    return Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="# Statement",
        reference_solution=reference,
        tests=[],
        hints=hint_list,
    )


# --- state -----------------------------------------------------------------


def test_state_starts_at_level_one() -> None:
    state = HintService.state(_problem())

    assert state.next_level == 1
    assert state.max_level == 5
    assert state.exhausted is False
    assert state.solution_available is True


def test_state_advances_with_usage() -> None:
    state = HintService.state(_problem(), levels_used=3)

    assert state.next_level == 4
    assert state.exhausted is False


def test_state_is_exhausted_after_all_levels() -> None:
    state = HintService.state(_problem(), levels_used=5)

    assert state.exhausted is True


def test_state_reports_no_hints_when_absent() -> None:
    state = HintService.state(_problem(hints=False))

    assert state.hints_available is False


# --- serving ---------------------------------------------------------------


def test_first_hint_is_level_one() -> None:
    result = HintService().next_hint(_problem())

    assert result.level == 1
    assert result.text == "stored hint 1"
    assert result.source == "stored"


def test_hints_advance_one_level_at_a_time() -> None:
    service = HintService()
    problem = _problem()

    levels = [
        service.next_hint(problem, levels_used=n).level for n in range(5)
    ]

    assert levels == [1, 2, 3, 4, 5]


def test_exhausted_ladder_raises() -> None:
    with pytest.raises(HintForbiddenError):
        HintService().next_hint(_problem(), levels_used=5)


def test_problem_without_hints_raises_unavailable() -> None:
    with pytest.raises(HintUnavailableError):
        HintService().next_hint(_problem(hints=False))


def test_level_five_is_marked_as_solution_reveal() -> None:
    result = HintService().get_level(_problem(), level=5)

    assert result.is_solution_reveal is True


def test_levels_below_five_are_not_solution_reveals() -> None:
    for level in range(1, 5):
        assert HintService().get_level(_problem(), level=level).is_solution_reveal is False


def test_out_of_range_level_is_rejected() -> None:
    service = HintService()

    with pytest.raises(HintForbiddenError):
        service.get_level(_problem(), level=0)
    with pytest.raises(HintForbiddenError):
        service.get_level(_problem(), level=6)


def test_stored_hints_work_without_a_provider() -> None:
    """Offline practice must still support the hint ladder."""
    result = HintService(provider=None).get_level(_problem(), level=2)

    assert result.source == "stored"


# --- generation fallback ---------------------------------------------------


def test_missing_stored_hint_is_generated() -> None:
    problem = _problem()
    problem.hints = [Hint(level=1, text="only level one")]
    provider = MockProvider(responses="a generated hint")

    result = HintService(provider).get_level(problem, level=2)

    assert result.source == "generated"
    assert result.text == "a generated hint"


def test_missing_stored_hint_without_provider_raises() -> None:
    problem = _problem()
    problem.hints = [Hint(level=1, text="only level one")]

    with pytest.raises(HintUnavailableError):
        HintService(provider=None).get_level(problem, level=3)


def test_generation_prompt_excludes_hidden_test_data() -> None:
    from app.schemas.test_case import TestCase, Visibility

    problem = _problem()
    problem.hints = []
    problem.tests = [
        TestCase(id="pub", name="Public", stdin="1 2\n", expected_stdout="3\n"),
        TestCase(
            id="sec",
            name="Hidden",
            visibility=Visibility.HIDDEN,
            stdin="999 111\n",
            expected_stdout="1110\n",
        ),
    ]
    provider = MockProvider(responses="hint text")

    HintService(provider).get_level(problem, level=1)

    prompt = provider.calls[0]["prompt"]
    assert "# Statement" in prompt
    # The hidden test's input and expected output must never be included.
    assert "999 111" not in prompt
    assert "1110" not in prompt


def test_level_four_prompt_requests_pseudocode_not_code() -> None:
    problem = _problem()
    problem.hints = []
    provider = MockProvider(responses="pseudocode guidance")

    HintService(provider).get_level(problem, level=4)

    prompt = provider.calls[0]["prompt"].lower()
    assert "pseudocode" in prompt
    assert "do not give final c code" in prompt


def test_empty_generated_hint_raises() -> None:
    problem = _problem()
    problem.hints = []

    with pytest.raises(HintUnavailableError):
        HintService(MockProvider(responses="   ")).get_level(problem, level=1)


def test_provider_failure_becomes_hint_unavailable() -> None:
    from app.ai.base import AuthError
    from app.ai.mock import failing_provider

    problem = _problem()
    problem.hints = []

    with pytest.raises(HintUnavailableError):
        HintService(failing_provider(AuthError("nope"), times=5)).get_level(problem, level=1)


def test_generated_hint_text_is_used_verbatim() -> None:
    problem = _problem()
    problem.hints = []
    provider = MockProvider(responses="  Trimmed guidance.  ")

    result = HintService(provider).get_level(problem, level=1)

    assert result.text == "Trimmed guidance."


# --- solution reveal -------------------------------------------------------


def test_solution_reveal_returns_reference() -> None:
    reference = "int main(void){return 42;}"
    problem = _problem(reference=reference)

    assert HintService().reveal_solution(problem) == reference


def test_solution_reveal_absent_raises() -> None:
    problem = _problem(reference="")

    with pytest.raises(HintUnavailableError):
        HintService().reveal_solution(problem)


def test_solution_level_constant_is_five() -> None:
    assert SOLUTION_LEVEL == 5
