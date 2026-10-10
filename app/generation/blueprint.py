"""Stage 1 — Exercise blueprint generation.

The blueprint is designed **before** the problem itself. It states what the
exercise is intended to teach, so the generator cannot fall back on producing a
generic textbook exercise from a topic label.

This is the answer to the architecture spec's diagnosis: *"The current weak
point is not primarily the user interface or compiler. It is the pedagogical
quality of generated problems."*
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.ai.base import AIProvider, AIProviderError
from app.ai.prompts_loader import PROMPT_VERSION, load_prompt
from app.ai.rate_limits import RetryPolicy, with_retry
from app.generation.prompts import parse_json_response
from app.schemas.pedagogy import DifficultyProfile, ExerciseRole, Pedagogy


class BlueprintError(RuntimeError):
    """Raised when a blueprint cannot be produced."""


#: JSON schema handed to the provider for structured blueprint output.
BLUEPRINT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "primary_objective": {"type": "string"},
        "secondary_objectives": {"type": "array", "items": {"type": "string"}},
        "prerequisites": {"type": "array", "items": {"type": "string"}},
        "target_reasoning_moves": {"type": "array", "items": {"type": "string"}},
        "likely_misconceptions": {"type": "array", "items": {"type": "string"}},
        "exercise_role": {
            "type": "string",
            "enum": [role.value for role in ExerciseRole],
        },
        "difficulty_profile": {
            "type": "object",
            "properties": {
                key: {"type": "integer"}
                for key in (
                    "concept_novelty", "reasoning_steps", "algorithm_selection",
                    "state_management", "edge_case_burden", "decomposition",
                    "reading_complexity", "prerequisite_depth",
                )
            },
        },
        "transfer_goal": {"type": "string"},
        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
        "solution_outline": {"type": "string"},
    },
    "required": [
        "primary_objective",
        "target_reasoning_moves",
        "likely_misconceptions",
        "exercise_role",
    ],
}


@dataclass(frozen=True)
class BlueprintRequest:
    """What the learner asked for."""

    topic: str
    difficulty: str = "beginner"
    target_skills: list[str] = None  # type: ignore[assignment]
    exercise_role: ExerciseRole = ExerciseRole.CORE_REASONING
    prerequisites: list[str] = None  # type: ignore[assignment]
    forbid: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Frozen dataclass: normalise mutable defaults via object.__setattr__.
        for field_name in ("target_skills", "prerequisites", "forbid"):
            if getattr(self, field_name) is None:
                object.__setattr__(self, field_name, [])


class BlueprintDesigner:
    """Produces an exercise blueprint from a learner request."""

    def __init__(
        self,
        provider: AIProvider,
        *,
        retry_policy: RetryPolicy | None = None,
        sleep=None,
    ) -> None:
        self.provider = provider
        self.retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleep

    def design(self, request: BlueprintRequest) -> Pedagogy:
        """Generate and validate a blueprint."""
        system = load_prompt("system_role") + "\n\n" + load_prompt("build_blueprint")
        prompt = self._build_prompt(request)

        def call():
            response = self.provider.generate(
                system=system,
                prompt=prompt,
                operation="build_blueprint",
                json_schema=BLUEPRINT_SCHEMA,
            )
            return response.text

        kwargs = {"policy": self.retry_policy}
        if self._sleep is not None:
            kwargs["sleep"] = self._sleep

        try:
            text = with_retry(call, **kwargs)
        except AIProviderError as exc:
            raise BlueprintError(f"provider failed while designing blueprint: {exc}") from exc

        try:
            payload = parse_json_response(text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise BlueprintError(f"blueprint was not parseable JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise BlueprintError("blueprint was not a JSON object")

        return self._validate(payload, request)

    # -- internals ---------------------------------------------------------

    def _build_prompt(self, request: BlueprintRequest) -> str:
        lines = [
            "Design an exercise blueprint for a learner practising C.",
            "",
            f"- Topic: {request.topic}",
            f"- Intended difficulty: {request.difficulty}",
            f"- Exercise role: {request.exercise_role.value}",
        ]

        if request.target_skills:
            lines.append(f"- Target skills: {', '.join(request.target_skills)}")
        if request.prerequisites:
            lines.append(
                f"- Prerequisites already taught (do not require others): "
                f"{', '.join(request.prerequisites)}"
            )
        if request.forbid:
            lines.append(f"- Forbidden constructs: {', '.join(request.forbid)}")

        lines += [
            "",
            "Remember: the primary objective must be an observable reasoning",
            "action, not a topic label. The tests will be designed from this",
            "blueprint, and the calibration checker will reject an exercise whose",
            "reference solution does not actually require the stated reasoning moves.",
        ]
        return "\n".join(lines)

    @staticmethod
    def _validate(payload: dict, request: BlueprintRequest) -> Pedagogy:
        """Validate a blueprint, rejecting the documented weak shapes."""
        role_value = payload.get("exercise_role") or request.exercise_role.value
        try:
            role = ExerciseRole(role_value)
        except ValueError:
            role = request.exercise_role

        moves = [str(m).strip() for m in payload.get("target_reasoning_moves") or [] if str(m).strip()]

        # Enforce the role's minimum reasoning moves. A blueprint that declares
        # too few would produce a warm-up labelled as a core problem.
        required = __import__(
            "app.schemas.pedagogy", fromlist=["MIN_REASONING_MOVES"]
        ).MIN_REASONING_MOVES.get(role, 2)

        if len(moves) < required:
            raise BlueprintError(
                f"blueprint declares {len(moves)} reasoning move(s) but role "
                f"{role.value} requires {required}"
            )

        profile_raw = payload.get("difficulty_profile")
        if not isinstance(profile_raw, dict):
            # Models sometimes return the profile as prose or a JSON string
            # rather than an object. Fall back to defaults rather than failing:
            # the profile is descriptive, not a correctness requirement.
            profile_raw = {}
        profile = DifficultyProfile.model_validate(
            {k: v for k, v in profile_raw.items() if isinstance(v, int) and not isinstance(v, bool)}
        )

        try:
            return Pedagogy(
                primary_objective=str(payload.get("primary_objective") or "").strip(),
                secondary_objectives=_as_list(payload.get("secondary_objectives")),
                prerequisites=_as_list(request.prerequisites or payload.get("prerequisites")),
                target_reasoning_moves=moves,
                likely_misconceptions=_as_list(payload.get("likely_misconceptions")),
                exercise_role=role,
                difficulty_profile=profile,
                transfer_goal=str(payload.get("transfer_goal") or "").strip(),
                acceptance_criteria=_as_list(payload.get("acceptance_criteria")),
                solution_outline=str(payload.get("solution_outline") or "").strip(),
            )
        except Exception as exc:
            raise BlueprintError(f"blueprint failed validation: {exc}") from exc


def blueprint_to_prompt_text(pedagogy: Pedagogy) -> str:
    """Render a blueprint as instructions for the problem-design stages."""
    lines = [
        "Approved exercise blueprint. Design the problem to require exactly this.",
        "",
        f"Primary objective: {pedagogy.primary_objective}",
    ]
    if pedagogy.secondary_objectives:
        lines.append(f"Secondary objectives: {', '.join(pedagogy.secondary_objectives)}")
    if pedagogy.prerequisites:
        lines.append(
            f"Prerequisites (assume known, require nothing else): "
            f"{', '.join(pedagogy.prerequisites)}"
        )
    lines.append("The learner must perform these reasoning moves:")
    for move in pedagogy.target_reasoning_moves:
        lines.append(f"  - {move}")
    if pedagogy.likely_misconceptions:
        lines.append("The test suite must catch these wrong approaches:")
        for misconception in pedagogy.likely_misconceptions:
            lines.append(f"  - {misconception}")
    if pedagogy.transfer_goal:
        lines.append(f"Afterwards the learner should find easier: {pedagogy.transfer_goal}")
    lines.append("")
    lines.append(
        "A reference solution that does not genuinely exercise these reasoning "
        "moves will be rejected by the calibration checker."
    )
    return "\n".join(lines)


def _as_list(value) -> list[str]:
    """Coerce a model-supplied value into a list of non-empty strings.

    Models sometimes return a single string or a comma-separated string where a
    list was requested. Iterating a bare string would produce one entry per
    character, so this normalises explicitly.
    """
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",")]
        return [p for p in parts if p]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def prompt_version() -> str:
    """The prompt asset version, recorded on generated problems."""
    return PROMPT_VERSION
