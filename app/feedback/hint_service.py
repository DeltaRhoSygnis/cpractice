"""Progressive hint service.

Design rules enforced here:

* Hints advance **one level at a time**. A learner cannot jump to level 5.
* Level 5 is the solution reveal and requires **explicit confirmation**.
* Stored hints are the source of truth. AI is only consulted when a level has
  no stored hint, and only ever sees public test data.
* Hidden test inputs and expected outputs are never included in a prompt.

If no provider is configured, stored hints still work: a learner can always
progress through the ladder offline (design decision #4).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.base import AIProvider, AIProviderError
from app.generation.prompts import build_hint_prompt
from app.schemas.problem import Problem

#: The level at which the reference solution may be revealed.
SOLUTION_LEVEL = 5


class HintUnavailableError(RuntimeError):
    """Raised when a hint cannot be served."""


class HintForbiddenError(HintUnavailableError):
    """Raised when a hint level is requested out of order."""


@dataclass(frozen=True)
class HintResult:
    """One served hint."""

    level: int
    text: str
    source: str  # "stored" | "generated"
    is_solution_reveal: bool = False


@dataclass(frozen=True)
class HintState:
    """How far a learner has progressed through the ladder."""

    next_level: int
    max_level: int
    hints_available: bool

    @property
    def exhausted(self) -> bool:
        return self.next_level > self.max_level

    @property
    def solution_available(self) -> bool:
        return self.max_level >= SOLUTION_LEVEL


class HintService:
    """Serves progressive hints for a problem."""

    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider

    # -- state -------------------------------------------------------------

    @staticmethod
    def state(problem: Problem, *, levels_used: int = 0) -> HintState:
        """Describe the ladder relative to how many hints were already used."""
        return HintState(
            next_level=max(1, levels_used + 1),
            max_level=problem.max_hint_level,
            hints_available=bool(problem.hints),
        )

    # -- serving -----------------------------------------------------------

    def next_hint(
        self,
        problem: Problem,
        *,
        levels_used: int = 0,
        learner_code: str = "",
        observed_failure: str = "",
    ) -> HintResult:
        """Serve the next hint in sequence.

        Raises :class:`HintForbiddenError` when the ladder is exhausted.
        """
        state = self.state(problem, levels_used=levels_used)

        if not state.hints_available:
            raise HintUnavailableError("this problem has no hints")

        if state.exhausted:
            raise HintForbiddenError("all hints have been used")

        return self.get_level(
            problem,
            level=state.next_level,
            learner_code=learner_code,
            observed_failure=observed_failure,
        )

    def get_level(
        self,
        problem: Problem,
        *,
        level: int,
        learner_code: str = "",
        observed_failure: str = "",
    ) -> HintResult:
        """Serve one specific level.

        A stored hint always wins. Only when none is stored is the provider
        consulted, and then only with public test context.
        """
        if level < 1 or level > SOLUTION_LEVEL:
            raise HintForbiddenError(f"hint level must be between 1 and {SOLUTION_LEVEL}")

        stored = problem.hint_for_level(level)
        if stored is not None:
            return HintResult(
                level=level,
                text=stored.text,
                source="stored",
                is_solution_reveal=level == SOLUTION_LEVEL,
            )

        # No stored hint: fall back to generation when a provider exists.
        if self.provider is None:
            raise HintUnavailableError(f"no hint available at level {level}")

        text = self._generate(problem, level, learner_code, observed_failure)
        return HintResult(
            level=level,
            text=text,
            source="generated",
            is_solution_reveal=level == SOLUTION_LEVEL,
        )

    def reveal_solution(self, problem: Problem) -> str:
        """Return the reference solution (an explicit, deliberate action)."""
        if not problem.reference_solution.strip():
            raise HintUnavailableError("this problem has no reference solution")
        return problem.reference_solution

    # -- generation --------------------------------------------------------

    def _generate(
        self,
        problem: Problem,
        level: int,
        learner_code: str,
        observed_failure: str,
    ) -> str:
        assert self.provider is not None  # guarded by caller

        prompt = build_hint_prompt(
            statement=problem.statement_md,
            level=level,
            learner_code=learner_code[:8000],
            observed_failure=observed_failure[:500],
        )

        try:
            response = self.provider.generate(
                system=_HINT_SYSTEM_PROMPT,
                prompt=prompt,
                operation="generate_hint",
            )
        except AIProviderError as exc:
            raise HintUnavailableError(f"could not generate a hint: {exc}") from exc

        text = response.text.strip()
        if not text:
            raise HintUnavailableError("provider returned an empty hint")
        return text


_HINT_SYSTEM_PROMPT = """\
You are a patient C programming tutor.

You give ONE hint at the requested level and nothing more. You never provide
complete C code, and you never reveal a hidden test's expected output.

Levels:
1. Concept - name the relevant idea or mental model only.
2. Direction - suggest how to decompose the problem. No code.
3. Trace - ask the learner to inspect a specific variable, iteration, or boundary.
4. Pseudocode - describe the algorithm in pseudocode. No final C code.
5. Approach - describe the solution in prose. Never paste a working program.

Respond with plain prose. Do not use code blocks. Be concise."""


def render_feedback(
    *,
    problem: Problem,
    passed: int,
    total: int,
    hint: HintResult | None = None,
) -> str:
    """Render a short, fact-first feedback line for the learner.

    Facts come from the checker; the hint is clearly attributed as guidance.
    """
    lines = [f"Tests: {passed} / {total} passed."]

    if hint is not None:
        lines.append("")
        lines.append(f"Hint (level {hint.level}):")
        lines.append(hint.text)

    return "\n".join(lines)
