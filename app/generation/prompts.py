"""Prompt construction for problem generation and hints.

Prompts are built here so provider adapters stay free of application logic and
prompt wording is testable without a network call.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

# --- JSON schema handed to the provider for structured output -------------

PROBLEM_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "difficulty": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]},
        "topics": {"type": "array", "items": {"type": "string"}},
        "target_skills": {"type": "array", "items": {"type": "string"}},
        "statement_md": {"type": "string"},
        "starter_code": {"type": "string"},
        "reference_solution": {"type": "string"},
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "visibility": {"type": "string", "enum": ["public", "hidden"]},
                    "stdin": {"type": "string"},
                    "expected_stdout": {"type": "string"},
                    "expected_exit_code": {"type": "integer"},
                    # Provenance: what each test is for. Required by the
                    # calibration standard, so the schema must ask for it.
                    "requirement_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "misconception_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "rationale": {"type": "string"},
                },
                "required": [
                    "id",
                    "name",
                    "visibility",
                    "stdin",
                    "expected_stdout",
                    "requirement_ids",
                    "misconception_ids",
                ],
            },
        },
        "hints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "level": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["level", "text"],
            },
        },
        "solution_explanation": {"type": "string"},
    },
    "required": [
        "id",
        "title",
        "difficulty",
        "statement_md",
        "starter_code",
        "reference_solution",
        "tests",
    ],
}

GENERATION_SYSTEM_PROMPT = """\
You are a careful C programming instructor and test designer.

You produce complete, self-contained C exercises that a deterministic test \
suite can grade. You never invent compiler-specific syntax and you always \
produce code that compiles cleanly as C11 with the standard library only.

Rules you must follow:
1. The exercise is a single standard-input/standard-output C program.
2. The reference solution must compile and produce exactly the expected output \
for every test case you provide.
3. Tests are declarative data. Never embed executable test scripts.
4. Include at least three public tests and at least two hidden tests.
5. Hidden tests must include genuine boundary cases, not repeats of public ones.
6. Expected stdout must match the reference solution byte for byte, including \
trailing newlines.
7. Hints must progress from concept to pseudocode. Level 5 must not contain \
the final C code.
8. Output must be valid JSON matching the provided schema. No prose outside \
the JSON.
9. Every test must carry `requirement_ids` and `misconception_ids`. Use the \
EXACT id strings declared in the blueprint's `likely_misconceptions` (the \
leading `MIS-...` token) so the package can prove each misconception is \
exercised.

Distribution code (`starter_code`) rules you must follow:
10. The starter code MUST compile cleanly as C11 (the learner can run the \
checker immediately). It may be incomplete, but it must be valid C.
11. The starter code MUST NOT pass the tests on its own. It must be missing at \
least one piece of real logic, so completing it is the task.
12. The starter code MUST contain at least one `TODO` comment marking exactly \
what the learner has to implement. Mark missing decisions, not formatting.
13. The starter code MUST NOT be the reference solution. Never ship the answer \
as the starter.

Consistency rules you must not break:
14. State the task once and mean it. Do not narrate doubt, self-correct, or \
write phrases such as "wait", "actually", or "correcting" anywhere in the \
statement, examples, or explanations.
15. Every example must be correct for the stated contract. Work each example \
out by hand from the specification before writing its expected output; an \
example that disagrees with the contract is a fatal error.
16. The examples, the tests, and the reference solution must all describe the \
same behaviour. If the reference and an expected value disagree, the package \
is wrong - fix it before replying, do not ship the disagreement.

Correctness beats cleverness. A simpler exercise with correct, mutually \
consistent statement, examples, tests, and reference is always better than an \
ambitious one with any inconsistency."""


@dataclass(frozen=True)
class GenerationRequest:
    """Parameters describing the exercise to generate."""

    topic: str = "loops"
    difficulty: str = "beginner"
    target_skills: list[str] = field(default_factory=list)
    constraints: str = ""
    stdin_format: str = "space-separated integers on a single line"
    stdout_format: str = "one value followed by a newline"
    hints_enabled: bool = True
    forbidden: list[str] = field(default_factory=list)

    def cache_parameters(self) -> dict:
        """Stable representation used for cache keys."""
        return {
            "topic": self.topic,
            "difficulty": self.difficulty,
            "target_skills": sorted(self.target_skills),
            "constraints": self.constraints,
            "stdin_format": self.stdin_format,
            "stdout_format": self.stdout_format,
            "hints_enabled": self.hints_enabled,
            "forbidden": sorted(self.forbidden),
        }


def build_generation_prompt(request: GenerationRequest) -> str:
    """Render the user prompt for a generation request."""
    skills = ", ".join(request.target_skills) if request.target_skills else "(you choose, appropriate to the topic)"
    forbidden = ", ".join(request.forbidden) if request.forbidden else "(none)"

    return f"""\
Create one C programming exercise with these parameters:

- Topic: {request.topic}
- Difficulty: {request.difficulty}
- Target skills: {skills}
- Input format: {request.stdin_format}
- Output format: {request.stdout_format}
- Additional constraints: {request.constraints or "(none)"}
- Forbidden constructs: {forbidden}
- Include progressive hints: {"yes" if request.hints_enabled else "no"}

Before returning, verify your own package:
- Re-read the statement and confirm every example agrees with it. Do not leave
  any example that you had to "correct" mid-thought; recompute and state the
  right answer once.
- Confirm the reference solution produces exactly the expected output for every
  test, and that examples and tests do not contradict each other.
- Confirm each test carries `requirement_ids` and `misconception_ids`, using the
  blueprint's declared `MIS-...` ids.
- Confirm `starter_code` compiles as C11, contains at least one `TODO` comment,
  does NOT pass the tests on its own, and is not the reference solution.

Deliver the exercise as JSON matching the schema. Include boundary cases among
the hidden tests, and make sure there are at least three public and at least
two hidden tests."""


def build_repair_prompt(
    *,
    problem: Problem,
    findings: list[dict],
    blueprint_text: str = "",
) -> str:
    """Render a repair request from a failing package and its findings.

    The findings are stated as facts, and the specification is declared the
    source of truth: fixing a symptom by weakening a test is forbidden.
    """
    finding_lines = "\n".join(
        f"- [{f.get('code', '?')}] {f.get('message', '')}" for f in findings
    )

    blueprint_section = f"\n---\n\n{blueprint_text}\n" if blueprint_text else ""

    return f"""\
The exercise below failed validation. Fix only what the findings identify.

## Findings

{finding_lines}

## The specification (source of truth)

{problem.statement_md}

## Reference solution

```c
{problem.reference_solution}
```

## Current tests

{json.dumps([t.model_dump(mode="json") for t in problem.tests], indent=2)}
{blueprint_section}
Return the corrected package as JSON matching the schema.

If a test failed, decide whether the *test* or the *reference* is wrong by
checking each against the specification above. Never weaken a test to make it
pass, and never change the specification to match buggy code. Every test must
carry `requirement_ids` and `misconception_ids`."""


def build_hint_prompt(
    *,
    statement: str,
    level: int,
    learner_code: str = "",
    observed_failure: str = "",
) -> str:
    """Render a prompt asking for one specific hint level."""
    code_section = f"\nThe learner's current attempt:\n```c\n{learner_code}\n```\n" if learner_code.strip() else ""
    failure_section = f"\nObserved test failure: {observed_failure}\n" if observed_failure else ""

    guidance = {
        1: "Identify the relevant concept or mental model only. Do not describe steps.",
        2: "Point toward a useful way to decompose the problem. Still no code.",
        3: "Ask the learner to inspect a specific variable, iteration, or boundary.",
        4: "Describe the algorithm in pseudocode. Do NOT give final C code.",
        5: "Describe the approach in prose. Do NOT paste a complete C solution.",
    }.get(level, "Give gentle, conceptual guidance.")

    return f"""\
A learner is working on this problem:

{statement}
{code_section}{failure_section}
Provide the level {level} hint. {guidance}

Respond with plain text only. Do not include code blocks."""


def parse_json_response(text: str) -> dict:
    """Parse a model response that should be JSON.

    Models sometimes wrap JSON in Markdown fences despite instructions; strip
    them before parsing rather than failing.
    """
    import json as _json

    cleaned = text.strip()

    if cleaned.startswith("```"):
        # Drop the opening fence (with optional language) and the closing fence.
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Last resort: isolate the outermost JSON object.
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]

    return _json.loads(cleaned)


def schema_as_json() -> str:
    """Render the schema for inclusion in a prompt if needed."""
    return json.dumps(PROBLEM_JSON_SCHEMA, indent=2)
