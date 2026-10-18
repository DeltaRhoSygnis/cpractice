# Contributing

## Ground rules

* **Tests are hermetic.** `tests/conftest.py` strips provider credentials and
  points settings at temp paths; the suite must never call a live AI API or
  need real keys to pass.
* **The gate decides, not the AI.** Anything that affects pass/fail,
  acceptance, or legality runs through a deterministic check
  (`app/generation/quality_gate.py`, `app/services/concepts.py`,
  `app/grading/evaluator.py`). Code that lets a model decide acceptance will
  be rejected.
* **Hidden test content never leaves the server.** API responses are
  deliberately narrower than the internal schemas (`app/api/problems.py`).

## Environment

Any Python ≥3.12 works; development on Termux (Android, python3.14) is
project-level supported.

```bash
pip install -r requirements.txt   # core stack (pins target py3.12; floats ok on 3.13+)
pip install "mcp==1.30.0"         # optional: only needed by the MCP server
pytest                            # full suite
pytest tests/test_import_api.py tests/test_mcp_server.py
```

## Project layout

| Path | Purpose |
|---|---|
| `app/api/` | Thin HTTP endpoints |
| `app/schemas/` | Pydantic problem/test/grading contracts |
| `app/generation/` | AI pipeline + deterministic quality gate |
| `app/grading/` | compiler → runner → comparator → evaluator |
| `app/services/` | application services (incl. `problem_import`) |
| `app/storage/` | SQLite + repositories |
| `app/mcp/` | optional MCP server (`python -m app.mcp.server`) |
| `tests/` | platform test suite (hermetic) |

## Pull requests

1. Include tests for behaviour change (hermetic, mocked).
2. `pytest` must pass locally — including on embedded environments, where
   resource-limit enforcement is skipped on purpose (see `docs/PLAN.md`).
3. New endpoints: document the contract in the module/endpoint docstring and
   mirror the response shapes of existing endpoints (e.g. import mirrors
   generate).
