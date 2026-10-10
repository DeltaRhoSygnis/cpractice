"""C stage curriculum map and operational skill definitions.

The engine needs a curriculum so exercises contribute to a progression rather
than accumulating as disconnected problems. Two parts:

* **Stages** — an ordered map of C concepts (plan section 5.1).
* **Skill tags** — each with an *operational definition*: what observable
  performance demonstrates the skill (plan section 5.2).

The plan is explicit that a topic label is not a skill. ``loop_bounds`` is only
meaningful if it says what a learner can *do*. Every tag here states that.

This is a starter map, configurable to a learner's own course sequence. It is
informed by the same broad principles as a demanding introductory course; it is
not a reproduction of any institution's syllabus.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Skill:
    """A skill tag with an operational definition."""

    tag: str
    name: str
    #: What observable performance demonstrates this skill.
    demonstrates: tuple[str, ...]
    #: The stage at which this skill is expected to be available.
    stage: int

    def is_observable(self) -> bool:
        """A skill is only useful if it states observable evidence."""
        return len(self.demonstrates) >= 2


@dataclass(frozen=True)
class Stage:
    """One stage of the C learning map."""

    index: int
    name: str
    concepts: tuple[str, ...]
    reasoning_practice: str


#: Ordered stage map. Exercises should not depend on a stage above the
#: learner's current one unless the problem is explicitly a challenge.
STAGES: tuple[Stage, ...] = (
    Stage(0, "Reading code", ("expressions", "types", "input_output"),
          "Predict output and trace state"),
    Stage(1, "Conditions", ("if_else", "boolean_expressions"),
          "Partition cases, find missing cases"),
    Stage(2, "Loops", ("for_loops", "while_loops", "loop_state"),
          "Count iterations, establish termination, derive bounds"),
    Stage(3, "Accumulation and counting",
          ("accumulation", "counting", "min_max", "predicates"),
          "Maintain a correct running state"),
    Stage(4, "Nested loops and patterns",
          ("nested_loops", "patterns", "row_column_relationships"),
          "Derive output dimensions and boundaries"),
    Stage(5, "Functions", ("functions", "parameters", "return_values", "decomposition"),
          "Separate responsibilities and define contracts"),
    Stage(6, "Arrays", ("arrays", "traversal", "indexing", "mutation"),
          "Bounds, invariants, multi-pass reasoning"),
    Stage(7, "Strings", ("strings", "char_arrays", "termination", "parsing_basics"),
          "Scan, count, classify, validate"),
    Stage(8, "Algorithms", ("linear_search", "sorting_concepts", "search_tradeoffs"),
          "Select and justify an approach"),
    Stage(9, "Memory and pointers",
          ("addresses", "pointers", "allocation"),
          "Trace memory and reason about ownership and validity"),
    Stage(10, "Data structures",
          ("structs", "linked_structures", "stacks_queues"),
          "Model data, manage state, analyse operations"),
    Stage(11, "Integration", ("mixed_concepts", "novel_problems"),
          "Decompose a novel problem independently"),
)


#: Skill tags with operational definitions. Each states observable performance,
#: never a claim about ability.
SKILLS: dict[str, Skill] = {
    "loop_bounds": Skill(
        tag="loop_bounds",
        name="Deriving loop bounds",
        stage=2,
        demonstrates=(
            "can determine the first and final iteration",
            "can explain whether the upper bound is inclusive or exclusive",
            "can count the expected number of iterations",
            "can detect a one-extra or one-missing iteration",
            "can justify the loop condition from the problem's domain",
        ),
    ),
    "loop_state": Skill(
        tag="loop_state",
        name="Maintaining loop state",
        stage=2,
        demonstrates=(
            "identifies what must remain true after each iteration",
            "updates state in the correct order relative to its use",
            "can trace the state value at a given iteration",
        ),
    ),
    "accumulation": Skill(
        tag="accumulation",
        name="Accumulating a result",
        stage=3,
        demonstrates=(
            "chooses a correct initial value for the accumulator",
            "updates the accumulator exactly once per required item",
            "can explain why the accumulator holds the right value at the end",
        ),
    ),
    "running_extremum": Skill(
        tag="running_extremum",
        name="Maintaining a running extremum",
        stage=3,
        demonstrates=(
            "initialises the extremum correctly for the stated input domain",
            "updates it exactly when a better value is found",
            "handles the first element without a special-case bug",
            "handles input where all values share the same sign or are equal",
        ),
    ),
    "condition_partitioning": Skill(
        tag="condition_partitioning",
        name="Partitioning cases correctly",
        stage=1,
        demonstrates=(
            "enumerates the distinct cases the specification requires",
            "orders conditions so no case is shadowed",
            "identifies an input that falls through every branch",
        ),
    ),
    "input_parsing": Skill(
        tag="input_parsing",
        name="Parsing structured input",
        stage=3,
        demonstrates=(
            "handles a count followed by that many values",
            "detects and handles insufficient input",
            "does not assume a fixed number of tokens beyond the contract",
        ),
    ),
    "array_traversal": Skill(
        tag="array_traversal",
        name="Traversing an array",
        stage=6,
        demonstrates=(
            "uses only valid indexes",
            "chooses correct start and end conditions",
            "processes each required element exactly as specified",
            "handles empty or minimum-size input when the contract permits it",
        ),
    ),
    "algorithm_decomposition": Skill(
        tag="algorithm_decomposition",
        name="Decomposing a problem",
        stage=5,
        demonstrates=(
            "identifies inputs, intermediate state, and the output",
            "breaks the task into logically separate steps",
            "chooses an order for those steps",
            "states how the algorithm makes progress toward completion",
        ),
    ),
    "string_scanning": Skill(
        tag="string_scanning",
        name="Scanning a C string",
        stage=7,
        demonstrates=(
            "respects the terminating null byte",
            "does not read past the terminator",
            "accumulates the required property in a single pass",
        ),
    ),
    "trace_execution": Skill(
        tag="trace_execution",
        name="Tracing execution",
        stage=0,
        demonstrates=(
            "predicts a variable's value at a stated point",
            "counts iterations of a loop",
            "identifies where behaviour diverges from the specification",
        ),
    ),
}


def stage_for_skill(tag: str) -> Stage | None:
    """The stage at which a skill becomes available."""
    skill = SKILLS.get(tag)
    if skill is None:
        return None
    return next((s for s in STAGES if s.index == skill.stage), None)


def skills_up_to(stage_index: int) -> list[Skill]:
    """Every skill available at or below a stage."""
    return [s for s in SKILLS.values() if s.stage <= stage_index]


def unknown_skills(tags: list[str]) -> list[str]:
    """Tags with no operational definition."""
    return [tag for tag in tags if tag not in SKILLS]


def skills_for_stage_concepts(concepts: list[str]) -> list[Skill]:
    """Skills whose stage covers any of the given concept tags."""
    indexes = {
        stage.index
        for stage in STAGES
        if any(concept in stage.concepts for concept in concepts)
    }
    return [s for s in SKILLS.values() if s.stage in indexes]


def validate_skills(tags: list[str]) -> tuple[list[str], list[str]]:
    """Split tags into (known, unknown).

    Unknown tags are surfaced rather than silently accepted: a tag with no
    operational definition cannot be assessed or targeted.
    """
    known = [tag for tag in tags if tag in SKILLS]
    unknown = [tag for tag in tags if tag not in SKILLS]
    return known, unknown
