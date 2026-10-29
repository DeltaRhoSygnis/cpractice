# Advanced usage

This file documents the operator and developer surfaces that are deliberately
not part of the learner README: the optional agent-tool server, the HTTP
interface, package import and generation, provider configuration, every
environment variable, LAN sharing, and packaging notes.

The default install is the browser app. Nothing here is required for offline
practice: saved problems, deterministic grading, stored hints, history, and
progress all work with no AI key and no optional SDK.

## MCP server and client configuration

The MCP server is an **optional extra**. The default install does not pull the
pinned `mcp==1.30.0` SDK. Install it with:

```bash
pipx install "cpractice[mcp] @ git+https://github.com/DeltaRhoSygnis/cpractice.git"
# or: uv tool install "cpractice[mcp] @ git+https://github.com/DeltaRhoSygnis/cpractice.git"
```

Start CPractice first (`cpractice start`), then run the server over stdio (what
MCP clients launch) or streamable HTTP:

```bash
cpractice-mcp                              # stdio
cpractice-mcp --transport streamable-http --port 8100
```

Both entry points are equivalent: the console script `cpractice-mcp` and
`python -m app.mcp.server`. Flags: `--transport {stdio,streamable-http}`,
`--host 127.0.0.1`, `--port 8100`, and `--base-url`. The CPractice API base URL
also comes from `CPRACTICE_URL` (default `http://127.0.0.1:8000`). The
streamable-HTTP transport binds to localhost by default.

If the optional SDK is missing, the command prints the exact install line and
exits 1 instead of raising `ModuleNotFoundError`.

The server exposes 17 tools: `health`, `curriculum`, `list_problems`,
`get_problem`, `submit`, `get_hint`, `reveal_solution`, `generate_problem`,
`create_problem_set`, `import_problem`, `get_progress`, `list_attempts`,
`get_attempt`, `get_recommendations`, `get_usage`, `get_known_concepts`, and
`set_known_concepts`. It is a thin HTTP client over the local API: the
deterministic grader remains authoritative, and `reveal_solution` requires an
explicit confirmation.

### opencode

Add this to `~/.config/opencode/opencode.json` (or the project's
`.opencode/opencode.json`):

```json
{
  "mcp": {
    "cpractice": {
      "type": "local",
      "command": ["cpractice-mcp"],
      "enable": true,
      "environment": { "CPRACTICE_URL": "http://127.0.0.1:8000" }
    }
  }
}
```

From a source checkout, use `"command": ["python", "-m", "app.mcp.server"]`
with the checkout as the working directory instead.

### Claude Desktop

In `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cpractice": {
      "command": "cpractice-mcp",
      "env": { "CPRACTICE_URL": "http://127.0.0.1:8000" }
    }
  }
}
```

Other MCP clients accept the same stdio command (`cpractice-mcp`, or
`python -m app.mcp.server` from a checkout). The server opens no new security
exposure: it binds to localhost and proxies requests to the same local API. See
[`SECURITY.md`](../SECURITY.md) for the trust model.

## HTTP API

The application serves its API under `/api` on the address printed by
`cpractice start` (default `http://127.0.0.1:8000`). Learner-facing problem
views withhold hidden test inputs and expected outputs; only their names and
the per-test verdicts are returned.

| Path | Method | Purpose |
|---|---|---|
| `/api/health` | GET | liveness, compile-and-run grading probe, AI status, resolved home |
| `/api/curriculum` | GET | the C concept stages and skill definitions |
| `/api/preferences/known-concepts` | GET/PUT | read or replace the learner's declared checklist |
| `/api/problems` | GET | list problem packages (summaries) |
| `/api/problems/{id}` | GET | one learner-facing problem view |
| `/api/problems/generate` | POST | run the AI pipeline and quality gate |
| `/api/problems/batch` | POST | prepare a shelf of problem sets in one batch provider run |
| `/api/problems/import` | POST | import a package through the same quality gate |
| `/api/problems/{id}/submit` | POST | deterministic grading |
| `/api/problems/{id}/hint` | POST | next or specific hint level |
| `/api/problems/{id}/solution` | POST | level-5 reveal, requires `{"confirm": true}` |
| `/api/attempts` | GET | recent attempts (`limit`, optional `problem_id`) |
| `/api/attempts/{id}` | GET | one attempt with per-test results |
| `/api/progress` | GET | practice summary |
| `/api/recommendations` | GET | next-practice suggestions (`limit`, optional `skill`) |
| `/api/usage` | GET | AI request and token usage, remaining daily budget |

Request shapes worth knowing:

- `POST /api/problems/{id}/submit`: `{"source": "int main(void) { ... }"}`.
  Optional fields are `hints_used` (0-5) and `predicted_stdout` (recorded and
  diffed, never graded).
- `POST /api/problems/{id}/hint`: `{"hints_used": 0}` for the next rung, or
  `{"level": 3}` for a specific one. `source` and `failure_summary` help draft a
  hint when no stored one exists.
- `PUT /api/preferences/known-concepts`: `{"known_concepts": ["variables"]}`.
  Unknown tags are rejected with 422; valid tags come from `/api/curriculum`.
- `POST /api/problems/import`: `{"package": { ... }, "overwrite": false}`; the
  package document is described below.

## Importing problem packages

Import a package authored elsewhere through the same deterministic gate that
screens AI-generated exercises. The request body wraps the package document:

```bash
jq -n --slurpfile package package.json \
  '{package: $package[0], overwrite: false}' \
  | curl -s -X POST http://127.0.0.1:8000/api/problems/import \
      -H 'Content-Type: application/json' --data-binary @-
```

The package document has metadata at the top level plus the content keys
`statement_md`, `starter_code`, `reference_solution`, `tests`, `hints`, and
optionally `solution_explanation` and `pedagogy` — the same shape as the
`problem.json` files under `app/seed_problems/`. The gate checks structure,
compiles and runs the reference solution against the declared tests, mutation
tests it, and checks concept legality for problem sets; a package that fails is
rejected. A rejected import returns `accepted: false` with its findings and is
never written to disk. An accepted package is written under `problems/` with
`status: validated` and a `quality_report.json`.

A package id that already exists returns 409 unless `overwrite: true` is sent.
The import endpoint writes files; do not expose it to untrusted clients (see
`SECURITY.md`).

## Generation and batch generation

Single generation runs the provider pipeline and the deterministic quality
gate. It needs a configured provider; otherwise the endpoint returns 503.

```bash
curl -s -X POST http://127.0.0.1:8000/api/problems/generate \
  -H 'Content-Type: application/json' \
  -d '{"topic": "loops", "difficulty": "beginner", "kind": "exercise"}'
```

`POST /api/problems/generate` accepts `topic`, `difficulty`
(`beginner|intermediate|advanced`), `target_skills`, `constraints`, `forbidden`,
`hints_enabled`, `use_cache`, `exercise_role`, `prerequisites`, `kind`
(`exercise|problem_set`), `new_concept`, and `assumed_known`. The response
reports `accepted`, `status`, the reference-solution result, and the gate's
errors and warnings. A package with an error-level finding is rejected.

Batch preparation (`POST /api/problems/batch`) prepares a shelf of problem sets
in one provider run. It is available only through the Gemini Batch API, so the
resolved provider must be Google (`AI_PROVIDER=google` plus a Google key);
otherwise it returns 503. The body holds up to 50 items (`{"items": [...]}`),
each with the generation fields plus an optional `custom_id`, and an optional
`job_id` for provenance. Per-item failures are reported rather than aborting the
shelf: batching changes transport only, and every item still passes the same
pipeline and gate.

In the browser, generation lives inside the collapsed **Advanced** disclosure
on the Dashboard. Import is available through `POST /api/problems/import` and
the MCP `import_problem` tool; it has no browser form, so the Advanced
disclosure does not pretend to offer one.

## Provider configuration

Configuration is read from the environment and from the `.env` file in the
resolved home directory. In an installed copy that is `~/.cpractice/.env`; in a
source checkout it is the repository-root `.env`. `cpractice version` prints the
home. `.env` is gitignored. The app writes only a fully commented `env.example`
on first run; it never writes a real `.env`.

Two adapters are available:

| `AI_PROVIDER` | Key | Default model |
|---|---|---|
| `kenari` (default) | `KENARI_API_KEY` | `deepseek-v4-1-flash` |
| `google` | `GOOGLE_API_KEY` | `gemini-2.0-flash` |

- **Kenari** is an OpenAI-compatible gateway (`KENARI_BASE_URL`, default
  `https://kenari.id/v1`). `AI_MODEL` is a catalog id; `:free` variants exist.
- **Google** uses the Gemini API through Google AI Studio.
- `AI_MODEL` always wins when set. When it is unset, the resolved provider's
  default model is used, so the model never belongs to the other provider. Note
  that copying the repository's `.env.example` sets
  `AI_MODEL=deepseek-v4-1-flash`; when using the Google adapter, change it to
  the Gemini model you intend to use.
- Provider selection: the selected provider is used when its key is present;
  otherwise any provider holding a key is used; with no key the app runs
  offline. The configured and active providers are reported by `/api/health`.
- Placeholder credential values are treated as unset. Empty strings, `change-me`,
  `your-kenari-key-here`, `your-google-key-here`, and any value beginning with
  `your-` never make the app claim AI is available.
- Generation and live hint drafting use the provider. Grading never does.

## Environment variables

All settings are environment variables; `.env` is only a convenient file for
them. Relative storage paths resolve under the resolved home directory.

| Variable | Default | Meaning |
|---|---|---|
| `APP_NAME` | `CPractice` | application name in responses |
| `APP_VERSION` | `0.1.0` | version string reported by the app |
| `DEBUG` | `false` | debug flag |
| `HOST` | `127.0.0.1` | server bind address |
| `PORT` | `8000` | server port |
| `CPRACTICE_HOME` | unset | overrides the resolved home; relative storage paths resolve under it |
| `CPRACTICE_HOST` | unset | `cpractice start` / `start.sh` bind override, above `HOST` |
| `CPRACTICE_PORT` | unset | `cpractice start` / `start.sh` port override, above `PORT` |
| `AI_PROVIDER` | `kenari` | `kenari` or `google` |
| `AI_MODEL` | `deepseek-v4-1-flash` | model id; explicit value always wins |
| `KENARI_API_KEY` | unset | Kenari gateway credential |
| `KENARI_BASE_URL` | `https://kenari.id/v1` | Kenari gateway base URL |
| `GOOGLE_API_KEY` | unset | Google AI Studio credential |
| `AI_MAX_RETRIES` | `3` | provider retry attempts |
| `AI_BACKOFF_BASE_SECONDS` | `2.0` | retry backoff base |
| `AI_MAX_CONCURRENT_REQUESTS` | `2` | concurrent provider requests |
| `AI_DAILY_REQUEST_BUDGET` | `0` | daily provider-request cap; 0 = unlimited |
| `CC_COMPILER` | `gcc` | C compiler used for grading and `doctor` |
| `CC_STANDARD` | `c11` | C language standard |
| `RUN_WALL_TIMEOUT_MS` | `3000` | per-run wall-clock limit |
| `RUN_MEMORY_LIMIT_MB` | `128` | per-run memory limit (best effort) |
| `RUN_MAX_OUTPUT_BYTES` | `65536` | per-run stdout/stderr cap |
| `DATABASE_PATH` | `data/cpractice.db` | SQLite database, relative to home |
| `PROBLEMS_DIR` | `problems` | problem shelf, relative to home |
| `WORKSPACES_DIR` | `workspaces` | transient grading workspaces, relative to home |
| `CPRACTICE_URL` | `http://127.0.0.1:8000` | API base URL read by the MCP server |

`cpractice start` resolves its bind as CLI flags > `CPRACTICE_HOST` /
`CPRACTICE_PORT` > `HOST` / `PORT` from settings > the defaults. A non-loopback
host requires `--allow-lan`.

`CPRACTICE_LIVE_AI=1` is a test-only switch that enables the opt-in live
provider test; the normal suite never calls a live API.

## LAN sharing

CPractice has **no authentication**. LAN sharing is supported only on a network
you trust, typically your own phone hotspot or home network:

```bash
cpractice start --host 0.0.0.0 --allow-lan
```

Without `--allow-lan`, a non-loopback bind is refused. With it, CPractice prints
the bind address and warns that it is reachable from the local network; open
`http://<your-lan-ip>:8000` from the other device. Anyone who can reach the port
can submit C that compiles and runs as your user, so do not use this on a public
network and do not forward the port from the internet. `SECURITY.md` is the
authoritative statement of this trust model; public hosting stays blocked until
the runner has a real sandbox.

From a source checkout, `CPRACTICE_HOST=0.0.0.0 ./start.sh` still works and
prints the usable LAN addresses (cellular interfaces are skipped on purpose).
The same rules apply if you expose the MCP server through streamable HTTP: it
proxies submissions to the same grader.

## Packaging and release notes

Build a wheel with:

```bash
python -m pip wheel --no-deps -w dist .
```

The wheel must contain the runtime assets, not just the Python modules:

- `app/web/*` — the plain HTML/CSS/JS interface and its icons;
- `app/seed_problems/*` — `c-sum-two-integers` and `pset-vote-tally`, including
  `problem.json`, `statement.md`, starter and reference C files;
- `app/ai/prompts/*.md` — the generation prompt templates;
- the `cpractice` and `cpractice-mcp` console entry points.

Wheel contents are checked by an opt-in gate:

```bash
CPRACTICE_BUILD_WHEEL=1 python3 -m pytest tests/test_packaging.py -q
```

It builds a wheel and asserts that `app/web/index.html`, `app/web/app.js`, and
both seed package directories are inside. Build isolation needs network access.

Seeding is one-way and safe to repeat. On startup, packages from
`app/seed_problems/` are copied into the problems directory only when their id
is absent from `problems/.seeded` and the target directory does not exist. An
existing package is never overwritten, and a package you deleted is not
resurrected. Packages added to the seed set in a later release are copied once.
The seed source ships inside the wheel, so first-run seeding works offline.

The MCP SDK stays an optional extra (`cpractice[mcp]`, pinned `mcp==1.30.0`), so
the default wheel install does not pull it. Release steps — version bump, tag,
wheel artifact, and the publish checklist — are in
[`docs/PUBLISH.md`](PUBLISH.md).
