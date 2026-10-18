"""MCP server for CPractice.

Exposes the CPractice platform over the Model Context Protocol so any MCP
client (Claude Desktop, opencode, Zed, a web agent gateway, ...) can drive the
practice loop: browse problems, submit C solutions to the **deterministic
grader**, request progressive hints, generate new problem sets from the
learner's own concept checklist, import problem packages, and review past
attempts.

Design contract (see README / docs/PLAN.md):

* AI generates and explains; deterministic software grades.
* The grader is authoritative. These tools never decide pass/fail — they call
  the local HTTP API and return its verdicts verbatim.
* ``reveal_solution`` is the level-5 escape hatch and is gated behind an
  explicit ``confirm=True``; it must only be used when a human learner asks
  for the answer.

The server is a thin HTTP client over the local API (default
``http://127.0.0.1:8000``, override with ``CPRACTICE_URL``). Start the
platform first::

    ./start.sh           # or: uvicorn app.main:app --host 127.0.0.1 --port 8000

Run the MCP server over stdio (what MCP clients launch)::

    python -m app.mcp.server            # stdio
    python -m app.mcp.server --transport streamable-http --port 8100

Requires the optional MCP SDK (``pip install "mcp==1.30.0"``, py3.13+ for the
py3.14-distribution marker set; see requirements.txt).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

MCP_BASE_URL_ENV = "CPRACTICE_URL"
DEFAULT_BASE_URL = "127.0.0.1:8000"
_LONG_TIMEOUT = 600.0  # generation/imports compile + mutate; be generous
_SHORT_TIMEOUT = 90.0


class CPracticeAPIError(RuntimeError):
    """A non-2xx response from the CPractice API."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"CPractice API returned {status_code}: {detail}")

    def to_payload(self) -> dict[str, Any]:
        detail = self.detail
        # FastAPI returns {"detail": "..."} on HTTPException; unwrap for tools.
        if isinstance(detail, dict) and set(detail) == {"detail"}:
            detail = detail["detail"]
        return {"ok": False, "status": self.status_code, "error": detail}


class CPracticeClient:
    """Thin async client for the local CPractice HTTP API."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def _call(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float = _SHORT_TIMEOUT,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                json=json_body,
                params=params,
            )
        if response.status_code >= 400:
            try:
                payload: Any = response.json()
            except ValueError:
                payload = response.text
            raise CPracticeAPIError(response.status_code, payload)
        return response.json()

    # -- typed convenience methods -----------------------------------------

    async def health(self) -> dict[str, Any]:
        return await self._call("GET", "/api/health")

    async def curriculum(self) -> dict[str, Any]:
        return await self._call("GET", "/api/curriculum")

    async def known_concepts(self) -> dict[str, Any]:
        return await self._call("GET", "/api/preferences/known-concepts")

    async def set_known_concepts(self, known_concepts: list[str]) -> dict[str, Any]:
        return await self._call(
            "PUT", "/api/preferences/known-concepts",
            json_body={"known_concepts": known_concepts},
        )

    async def list_problems(self) -> dict[str, Any]:
        return await self._call("GET", "/api/problems")

    async def get_problem(self, problem_id: str) -> dict[str, Any]:
        return await self._call("GET", f"/api/problems/{problem_id}")

    async def submit(
        self,
        problem_id: str,
        source: str,
        predicted_stdout: str | None = None,
        hints_used: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"source": source}
        if predicted_stdout is not None:
            body["predicted_stdout"] = predicted_stdout
        if hints_used is not None:
            body["hints_used"] = hints_used
        return await self._call(
            "POST", f"/api/problems/{problem_id}/submit", json_body=body,
            timeout=_LONG_TIMEOUT,
        )

    async def hint(
        self,
        problem_id: str,
        level: int | None = None,
        hints_used: int | None = None,
        source: str | None = None,
        failure_summary: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if level is not None:
            body["level"] = level
        if hints_used is not None:
            body["hints_used"] = hints_used
        if source is not None:
            body["source"] = source
        if failure_summary is not None:
            body["failure_summary"] = failure_summary
        return await self._call(
            "POST", f"/api/problems/{problem_id}/hint", json_body=body,
        )

    async def reveal_solution(self, problem_id: str) -> dict[str, Any]:
        return await self._call(
            "POST", f"/api/problems/{problem_id}/solution", json_body={"confirm": True},
        )

    async def generate(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._call(
            "POST", "/api/problems/generate", json_body=body, timeout=_LONG_TIMEOUT,
        )

    async def import_problem(
        self, package: dict[str, Any], overwrite: bool = False
    ) -> dict[str, Any]:
        return await self._call(
            "POST", "/api/problems/import",
            json_body={"package": package, "overwrite": overwrite},
            timeout=_LONG_TIMEOUT,
        )

    async def list_attempts(
        self, problem_id: str | None = None, limit: int = 20
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if problem_id:
            params["problem_id"] = problem_id
        return await self._call("GET", "/api/attempts", params=params)

    async def get_attempt(self, attempt_id: int) -> dict[str, Any]:
        return await self._call("GET", f"/api/attempts/{attempt_id}")

    async def progress(self) -> dict[str, Any]:
        return await self._call("GET", "/api/progress")

    async def recommendations(self, skill: str | None = None, limit: int = 5) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if skill:
            params["skill"] = skill
        return await self._call("GET", "/api/recommendations", params=params)

    async def usage(self) -> dict[str, Any]:
        return await self._call("GET", "/api/usage")


_active_client: CPracticeClient | None = None


def configure_client(client: CPracticeClient) -> None:
    """Point the module-level tools at ``client`` (also: test seam)."""
    global _active_client
    _active_client = client


def _get_client() -> CPracticeClient:
    global _active_client
    if _active_client is None:
        _active_client = CPracticeClient(
            os.environ.get(MCP_BASE_URL_ENV) or f"http://{DEFAULT_BASE_URL}"
        )
    return _active_client


# --- frontier derivation (used by create_problem_set) ------------------------

def derive_frontier_pair(curriculum: dict[str, Any], known: list[str]) -> dict[str, Any]:
    """Derive the next (new_concept, assumed_known) pair from the ladder.

    Mirrors the rule the platform enforces for legal problem sets (spec S3):
    the first concept on the staircase the learner has NOT marked known is the
    new concept; already-known concepts from earlier stages form
    ``assumed_known`` (capped at 4, closest first).
    """
    known_set = set(known)
    stages = sorted(curriculum.get("stages", []), key=lambda s: s.get("index", 0))

    new_concept: str | None = None
    new_stage: int | None = None
    for stage in stages:
        for concept in stage.get("concepts", []):
            if concept not in known_set:
                new_concept = concept
                new_stage = stage.get("index")
                break
        if new_concept:
            break

    assumed: list[str] = []
    if new_stage is not None:
        for stage in stages:
            if stage.get("index", 0) < new_stage:
                for concept in stage.get("concepts", []):
                    if concept in known_set and concept not in assumed:
                        assumed.append(concept)
    if not assumed:
        for concept in known:
            if concept not in assumed:
                assumed.append(concept)
    return {
        "new_concept": new_concept,
        "new_stage": new_stage,
        "assumed_known": assumed[:4],
    }


# --- tool implementations (kept module-level for direct testing) -------------

async def tool_health() -> dict[str, Any]:
    """Health of the CPractice server (compiler, AI provider, storage)."""
    return await _get_client().health()


async def tool_curriculum() -> dict[str, Any]:
    """The 12-stage C curriculum: every stage, concept, and skill."""
    return await _get_client().curriculum()


async def tool_list_problems() -> dict[str, Any]:
    """List the saved problem packages as summaries."""
    return await _get_client().list_problems()


async def tool_get_problem(problem_id: str) -> dict[str, Any]:
    """Read one problem's learner-facing view: statement, starter code, and the
    public tests. Hidden test input/expected output are never exposed."""
    return await _get_client().get_problem(problem_id)


async def tool_submit(
    problem_id: str,
    source: str,
    predicted_stdout: str | None = None,
    hints_used: int | None = None,
) -> dict[str, Any]:
    """Submit C source to the deterministic grader. Returns the verdict, per-
    test pass/fail, and a failure summary. Optionally record the learner's
    predicted_stdout (diffed, never graded). The grader is authoritative."""
    return await _get_client().submit(problem_id, source, predicted_stdout, hints_used)


async def tool_get_hint(
    problem_id: str,
    level: int | None = None,
    hints_used: int | None = None,
    source: str | None = None,
    failure_summary: str | None = None,
) -> dict[str, Any]:
    """Request the next progressive hint (one level at a time). Pass the
    failing source and failure_summary the grader produced so the hint matches
    where the learner actually is."""
    return await _get_client().hint(problem_id, level, hints_used, source, failure_summary)


async def tool_reveal_solution(problem_id: str, confirm: bool = False) -> dict[str, Any]:
    """Reveal the reference solution for a problem. Gated: only call this with
    confirm=True when the learner explicitly asks for the answer — otherwise
    use get_hint to keep them inside the learning ladder."""
    if not confirm:
        return {
            "ok": False,
            "error": "refusing to reveal the reference solution: resend with "
            "confirm=true only when the learner explicitly asks for the answer",
        }
    return await _get_client().reveal_solution(problem_id)


async def tool_generate_problem(
    topic: str,
    difficulty: str = "beginner",
    kind: str = "exercise",
    new_concept: str | None = None,
    assumed_known: list[str] | None = None,
    constraints: str = "",
) -> dict[str, Any]:
    """Generate one new problem through the AI pipeline. The deterministic
    quality gate decides whether it is accepted; rejections come back with
    their findings. Costs one AI provider request."""
    body: dict[str, Any] = {
        "topic": topic,
        "difficulty": difficulty,
        "kind": kind,
        "constraints": constraints,
    }
    if new_concept is not None:
        body["new_concept"] = new_concept
    if assumed_known is not None:
        body["assumed_known"] = assumed_known
    return await _get_client().generate(body)


async def tool_create_problem_set(
    dry_run: bool = False,
    topic: str | None = None,
    difficulty: str = "beginner",
) -> dict[str, Any]:
    """Run the whole problem-set creation loop: read the curriculum and the
    learner's known-concepts checklist, derive a legal (new_concept,
    assumed_known) frontier pair, and generate a problem set the learner can
    answer. With dry_run=True, return the derived plan without spending an AI
    request."""
    client = _get_client()
    curriculum = await client.curriculum()
    checklist = await client.known_concepts()
    derived = derive_frontier_pair(curriculum, checklist.get("known_concepts", []))
    if derived["new_concept"] is None:
        return {
            "ok": False,
            "error": "the known-concepts checklist covers the whole staircase; "
            "there is no new concept left to introduce",
        }
    plan = {
        "topic": topic or derived["new_concept"],
        "difficulty": difficulty,
        "kind": "problem_set",
        "new_concept": derived["new_concept"],
        "assumed_known": derived["assumed_known"],
    }
    if dry_run:
        return {"ok": True, "dry_run": True, "plan": plan,
                "known_concepts": checklist.get("known_concepts", [])}
    return await client.generate(plan)


async def tool_import_problem(
    package: dict[str, Any], overwrite: bool = False
) -> dict[str, Any]:
    """Import one problem package into CPractice.

    ``package`` is a single JSON document shaped like problem.json (metadata
    at the top level plus the content keys statement_md / starter_code /
    reference_solution / tests / hints). The deterministic quality gate grades
    the package; only valid packages are written to disk. Rejections return
    the gate findings."""
    return await _get_client().import_problem(package, overwrite)


async def tool_get_progress() -> dict[str, Any]:
    """Summary of practice history in observed terms (attempts, solved, pass
    rate)."""
    return await _get_client().progress()


async def tool_list_attempts(
    problem_id: str | None = None, limit: int = 20
) -> dict[str, Any]:
    """List recent attempts (newest first), optionally for one problem."""
    return await _get_client().list_attempts(problem_id, limit)


async def tool_get_attempt(attempt_id: int) -> dict[str, Any]:
    """Read one attempt with its per-test results (for a post-mortem review)."""
    return await _get_client().get_attempt(attempt_id)


async def tool_get_recommendations(
    skill: str | None = None, limit: int = 5
) -> dict[str, Any]:
    """Evidence-based next-exercise suggestions (weakness ranking + sequencer
    role). Supply an optional ``skill`` tag to target one skill."""
    return await _get_client().recommendations(skill, limit)


async def tool_get_usage() -> dict[str, Any]:
    """AI provider usage and remaining daily request budget."""
    return await _get_client().usage()


async def tool_get_known_concepts() -> dict[str, Any]:
    """The learner's known-concepts checklist and the frontier stage it
    implies."""
    return await _get_client().known_concepts()


async def tool_set_known_concepts(
    known_concepts: list[str] | None = None, through_stage: int | None = None
) -> dict[str, Any]:
    """Replace the learner's known-concepts checklist (the explicit 'known'
    side of the concept ladder). Supply the tag list directly, or
    ``through_stage`` to mark every concept of stages 0..N as known."""
    if through_stage is not None and not known_concepts:
        curriculum = await _get_client().curriculum()
        stages = sorted(curriculum.get("stages", []), key=lambda s: s.get("index", 0))
        known_concepts = [
            concept
            for stage in stages
            if stage.get("index", 0) <= through_stage
            for concept in stage.get("concepts", [])
        ]
    if not known_concepts:
        return {"ok": False, "error": "provide known_concepts or through_stage"}
    return await _get_client().set_known_concepts(list(known_concepts))


TOOL_FUNCS = {
    "health": tool_health,
    "curriculum": tool_curriculum,
    "list_problems": tool_list_problems,
    "get_problem": tool_get_problem,
    "submit": tool_submit,
    "get_hint": tool_get_hint,
    "reveal_solution": tool_reveal_solution,
    "generate_problem": tool_generate_problem,
    "create_problem_set": tool_create_problem_set,
    "import_problem": tool_import_problem,
    "get_progress": tool_get_progress,
    "list_attempts": tool_list_attempts,
    "get_attempt": tool_get_attempt,
    "get_recommendations": tool_get_recommendations,
    "get_usage": tool_get_usage,
    "get_known_concepts": tool_get_known_concepts,
    "set_known_concepts": tool_set_known_concepts,
}

_INSTRUCTIONS = """\
CPractice is a C programming practice platform with a **deterministic grader**.
Contract: AI generates and explains; deterministic software grades. You are a
tutor in this loop, never the authority on correctness.

The intended loop:
1. `create_problem_set` (or `list_problems` / `get_recommendations`) to pick
   work matched to the learner's own known-concepts checklist.
2. Show the problem's `get_problem` view; the learner writes C on their side.
3. `submit` their source (optionally with `predicted_stdout`) — the grader's
   verdict is final.
4. On failure, walk the hint ladder with `get_hint` before anything else.
5. `reveal_solution` only on an explicit learner request (it is the last rung).
6. For post-mortems, `list_attempts` / `get_attempt` give per-test results.

Never fabricate a pass/fail verdict: report what `submit` returned.
"""


def build_server(base_url: str | None = None):
    """Build the MCPServer with every CPractice tool registered."""
    from mcp.server.fastmcp import FastMCP

    configure_client(CPracticeClient(base_url or _default_base_url()))

    mcp = FastMCP(
        name="cpractice",
        instructions=_INSTRUCTIONS,
    )
    for name, fn in TOOL_FUNCS.items():
        mcp.tool(name=name)(fn)
    return mcp


def _default_base_url() -> str:
    configured = os.environ.get(MCP_BASE_URL_ENV)
    if configured:
        return configured
    return f"http://{DEFAULT_BASE_URL}"


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m app.mcp.server", description=__doc__.splitlines()[1]
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="stdio (MCP client-launched) or streamable-http (localhost HTTP)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument(
        "--base-url",
        default=None,
        help="CPractice API base URL (also via CPRACTICE_URL env)",
    )
    args = parser.parse_args(argv)

    mcp = build_server(args.base_url)
    # Keep the untranslated settings consistent with the CLI flags.
    mcp.settings.host = args.host
    mcp.settings.port = args.port

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
