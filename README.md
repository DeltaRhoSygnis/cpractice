# CPractice

![CI](https://github.com/DeltaRhoSygnis/cpractice/actions/workflows/tests.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)
![C](https://img.shields.io/badge/language-C11-grey.svg)

**AI-powered C programming practice with deterministic automated grading.**

**Core principle: AI generates and explains. Deterministic software grades.**

The agent is never the authority on correctness. A package only ships after a
deterministic quality gate validates it — structure, reference compilation,
test discrimination (mutation testing), concept legality against the learner's
own checklist — and every submission is graded by the same evaluator. A model
being down, wrong, or cheap cannot change a verdict.

---

## Contents

- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Used with free AI coding agents](#used-with-free-ai-coding-agents)
- [MCP server](#mcp-server)
- [The practice loop](#the-practice-loop)
- [HTTP API](#http-api)
- [Importing problem packages](#importing-problem-packages)
- [Configuration](#configuration)
- [Project layout & grading pipeline](#project-layout--grading-pipeline)
- [Testing](#testing)
- [Status](#status)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

## What it does

CPractice is a web app and an agent toolset where a learner:

1. Gets a problem (generated with the **AI pipeline**, imported, or authored by hand)
2. Writes a C solution in their own editor
3. Submits the source and receives **repeatable, deterministic** per-test verdicts. Optionally, the learner predicts outputs before verification (`predicted_stdout` is diffed, never admitted as evidence)
4. Requests progressive hints (_, ladder, level 1 onward, author-supplied or AI-drafted; the reference solution stays behind an explicit level-5 reveal_)
5. Reviews the attempt history post-hoc and receives evidence-based next practice suggestions

The **concept ladder** forms pedagogical structure: every problem set integrates exactly one *new* concept with already-known concepts, and its legality is checked deterministically against the learner's declared checklist — the "assumed unknown" is matched against that, so a pset can never assume knowledge that was not declared.

Deterministic both in grading and deck fitting means a free-tier agent suffices; the pedagogy contract is not the agent's job to remember.

## Quick start

### Local (Linux, Termux/Android — first-class support)

```bash
git clone https://github.com/DeltaRhoSygnis/cpractice.git
cd cpractice
pip install -r requirements.txt
cp .env.example .env      # add an AI provider key — see Configuration
./start.sh                # http://127.0.0.1:8000
```

or without the helper: `uvicorn app.main:app --host 127.0.0.1 --port 8000`.

> **Termux caveat:** compiled binaries cannot execute on shared Android
> storage (`noexec` mount). Keep the repo under the Termux home directory.

### Use it from your laptop over the phone's hotspot

The server can be shared with devices you own on the phone's hotspot
(no auth — see SECURITY.md "LAN sharing" for the rules):

```bash
CPRACTICE_HOST=0.0.0.0 ./start.sh
```

`start.sh` then prints every usable LAN address; open `http://<phone-ip>:8000`
from the laptop. Bluetooth tethering works identically once the PAN interface
appears in `ip -4 -o addr show`. From the laptop you can even run the agent
stack *there* while the grader stays on the phone:

```bash
pip install "mcp==1.30.0"
CPRACTICE_URL=http://<phone-ip>:8000 python -m app.mcp.server
# point opencode/Claude Desktop/Cline at this localhost MCP entry point
```

### GitHub Codespaces

The repo ships a `.devcontainer`, so C compilation works there too. Preflight
secrets check, then:

```bash
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### pip install (library/CLI use)

```bash
pip install "cpractice[mcp] @ git+https://github.com/DeltaRhoSygnis/cpractice.git"
cpractice-mcp --help      # MCP server entry point
```

## Used with free AI coding agents

The design makes this practical: the **deterministic grader provides the
verdicts**, so the agent only generates, explains, and walks the hint ladder.
A free model is enough for that.

### Outline

1. `./start.sh` — platform up on `http://127.0.0.1:8000`
2. Give the agent one of the entry points below (MCP tools, or plain HTTP).
3. Drive the loop with a prompt like:

> "Set my known-concepts through stage 2, then use create_problem_set for my
> frontier and give me the problem. I'll code and you submit my solution via
> submit; walk me up the hint ladder with get_hint when I fail — never
> reveal_solution unless I explicitly ask."

The concept-ladder checks and grader that the agent calls happen
**server-side**: an agent cannot skip the ladder or grade its own submit.

### opencode (free models included)

Add the MCP server in `~/.config/opencode/opencode.json` (or the project's
`.opencode/opencode.json`):

```json
{
  "mcp": {
    "cpractice": {
      "type": "local",
      "command": ["python", "-m", "app.mcp.server"],
      "enable": true,
      "environment": { "CPRACTICE_URL": "http://127.0.0.1:8000" }
    }
  }
}
```

opencode delegates model choice to you, so free models are fine (DeepSeek,
Qwen Coder, Gemini Flash, Kimi, GLM — via its OpenRouter/Google/etc.
providers). Any of them can drive these tools, since correctness comes from
the server, not the model.

> The author's setup uses exactly this shape against a cpractice server on
> the same box, with the opencode instance running on free models.

### Other free MCP-capable agents

Point the MCP server at the same stdio entry point:

| Agent | Where the config goes |
|---|---|
| Claude Desktop | `claude_desktop_config.json` (JSON below [here](#mcp-server)) |
| Cline / Roo Code / Kilo Code | `cline_mcp_settings.json` → command `python`, args `-m app.mcp.server` |
| Continue.dev | `~/.continue/config.yaml` → `mcpServers` entry, command-mode |
| Zed | `settings.json` → `context_servers` entry |

No MCP support? Everything above is plain HTTP — a free-model agent with a
shell and `curl` can drive the whole loop: `POST /api/problems/{id}/submit`
returns the verdict, `POST /{id}/hint` walks the ladder, `GET /api/attempts`,
`GET /api/recommendations`.

### Agent costs

- **Generation** (optional): needs a provider key; free tiers exist (Kenari
  free catalog models, Google AI Studio free tier). The app runs
  **generationless** too — offline practice with saved/imported problems is a
  first-class path (see the `.env.example` for the budgeting knobs: caps via
  `AI_DAILY_REQUEST_BUDGET`, retries, concurrency).
- **Hints** (optional): provider-backed when a key exists; stored hints
  always work and require nothing.
- **Grading**: costs **nothing** and uses **no AI**, ever.

## MCP server

17 tools exposing the loop to any MCP client — problems, the grader, the hint
ladder, gated `reveal_solution`, `create_problem_set` (legal frontier pair
derived from the checklist), `import_problem`, progress/attempts/reviews,
curriculum, checklist. stdio for client-launched agents, or streamable-http:

```bash
python -m app.mcp.server                     # stdio
CPRACTICE_URL=http://127.0.0.1:8000 \
  python -m app.mcp.server --transport streamable-http --port 8100
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "cpractice": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/path/to/cpractice",
      "env": { "CPRACTICE_URL": "http://127.0.0.1:8000" }
    }
  }
}
```

The MCP server is a thin HTTP client over this same API: it binds only to
localhost and opens **no new security exposure** — see
[`SECURITY.md`](SECURITY.md).

## The practice loop

```text
 known-concepts checklist (you declare it; the platform never guesses)
           │
           ▼
 derive legal frontier pair   (new_concept ⊄ known, assumed ⊆ known)
           │
           ▼
 AI pipeline generates → deterministic quality gate
      (structure · reference compile+run all tests · mutation testing
       · concept legality vs YOUR checklist · resource limits)
           │  accepted only when no error-level finding exists
           ▼
 submit (learner's C source)
           │
           ▼
 compile → isolated runner (timeout/RLIMIT/output cap) → comparator
           │
           ▼
 per-test verdicts + failure summary   ← also records predicted_stdout diffs
           │
           ▼
 hint ladder (1..4/5) / progressive reveal (5, explicit only)
```

## Problem sets

A **problem set** (`kind: "problem_set"`) is the full CS50-style unit. It is
prepared in one go — statement, distribution code, reference solution, tagged
test suite, checker, requirements and hints — and only then presented.

- **Distribution code.** The package ships a starter scaffold with `TODO`
  markers (and optionally a `hint/` variant beside it). The gate rejects a
  starter that already passes its own tests — otherwise the learner would be
  handed the answer.
- **One new concept, combined with known ones.** The pset declares a concept
  pair: `new_concept` must not be on the learner's checklist, and every
  `assumed_known` concept must be. The check is deterministic and runs against
  the checklist *you* declare — the platform never guesses.
- **A checker, not just tests.** Every pset presents a `check50`-style report:
  an ordered list of `exists` → `compiles` → per-test checks, each with a
  pass/blocked state and a cause. A compile failure blocks the behavioural
  checks rather than failing them, and a check never carries test data, so
  hidden stdin and expected output cannot leak through the report.
- **Predict, then verify.** Before submitting, the learner states what the
  program will print. The submission diffs predicted vs expected vs actual
  and may cite a *declared* misconception id. The prediction is never evidence:
  the verdict, pass counts, and per-test results are identical with and
  without it.
- **Batch shelf preparation.** Because a whole pset is prepared up front,
  psets can be generated in one provider run (`POST /api/problems/batch`).
  Batching is a transport change only — every item goes through the same
  pipeline and the same quality gate, so it can never lower the bar. A failed
  item is recorded and the shelf still completes.

## HTTP API

| Path | Method | Purpose |
|---|---|---|
| `/api/health` | GET | compiler/AI/storage status |
| `/api/curriculum` | GET | the 12-stage C concept ladder |
| `/api/preferences/known-concepts` | GET/PUT | the learner's declared checklist |
| `/api/problems` | GET | list problem packages |
| `/api/problems/{id}` | GET | learner-facing view (hidden test content is withheld) |
| `/api/problems/generate` | POST | runs the AI pipeline + quality gate |
| `/api/problems/batch` | POST | prepares a shelf of psets in one batch provider run (same pipeline, same gate) |
| `/api/problems/import` | POST | import a package through the same gate |
| `/api/problems/{id}/submit` | POST | deterministic grading |
| `/api/problems/{id}/hint` | POST | next hint level |
| `/api/problems/{id}/solution` | POST | level-5 reveal (`{"confirm": true}`) |
| `/api/attempts` / `/api/attempts/{id}` | GET | attempt history / per-test results |
| `/api/progress` / `/api/recommendations` | GET | trends / next-practice suggestions |

The server also ships a small local web UI at `/` for browser practice.

## Importing problem packages

Bring a problem authored elsewhere (another instance, a human, a web agent)
into CPractice via `POST /api/problems/import`. The body is one JSON document
shaped like the packages on disk — metadata at the top level plus the content
keys (`statement_md`, `starter_code`, `reference_solution`, `tests`,
`hints`) — and the same deterministic quality gate that screens AI-generated
packages runs over it. Rejected imports return the gate's findings and are
**never** written to disk; accepted ones land with `status: validated`:

```bash
curl -s -X POST http://127.0.0.1:8000/api/problems/import \
  -H 'Content-Type: application/json' \
  -d @package.json && echo
```

## Configuration

All configuration comes from environment variables (see `.env.example`).
**Never commit real secrets.** `.env` is gitignored.

| Variable | Purpose |
|---|---|
| `AI_PROVIDER` | `kenari` (default) or `google` |
| `AI_MODEL` | model id, e.g. `deepseek-v4-1-flash` (Kenari catalog; `:free` variants exist) |
| `KENARI_API_KEY` | Kenari gateway key (free-tier catalog models) |
| `GOOGLE_API_KEY` | Google AI Studio key (free tier available) |
| `AI_DAILY_REQUEST_BUDGET` | provider-request cap for the day (0 = unlimited) |
| `CC_COMPILER` / `CC_STANDARD` | C compiler + language standard |
| `RUN_WALL_TIMEOUT_MS` / `RUN_MEMORY_LIMIT_MB` / `RUN_MAX_OUTPUT_BYTES` | grading limits |
| `HOST` / `PORT` | server bind — keep `127.0.0.1` (see SECURITY.md) |

## Project layout & grading pipeline

```text
cpractice/
├── .devcontainer/        # Codespaces definition + setup script
├── app/                  # FastAPI application
│   ├── api/              # HTTP endpoints (thin)
│   ├── schemas/          # Pydantic problem/test/grading contracts
│   ├── ai/               # provider adapters (+ prompt templates)
│   ├── generation/       # pipeline + deterministic quality gate
│   ├── grading/          # compiler → runner → comparator → evaluator
│   ├── feedback/         # reporter + hint service
│   ├── storage/          # SQLite + repositories
│   ├── services/         # application services (incl. import)
│   └── mcp/              # optional MCP server (app.mcp.server)
├── web/                  # offline HTML/CSS/JS frontend
├── problems/             # versioned problem packages (fixtures tracked)
├── data/                 # SQLite database (gitignored)
├── workspaces/           # transient grading workspaces (gitignored)
├── tests/                # hermetic pytest suite (mocked AI, real gcc)
└── docs/                 # PLAN, engine design, PUBLISH runbook
```

Grading runs at submission time: gcc → isolated runner (wall-clock + CPU
limits, output caps, workspaces) → comparator (`exact_normalized` /
`whitespace_tolerant`) → evaluator verdicts. The same evaluator powers the
quality gate's reference check and mutation testing, so what grades you is
the thing that screened the exercise.

## Testing

```bash
pytest                # hermetic: mocked AI providers, isolated settings
```

No live keys are consulted by the suite (credential vars are stripped in
`tests/conftest.py`). The 3 `skipped` tests exercise live provider paths and
require explicit configuration.

## Status

- **Shipped**: generation with gated acceptance, deterministic grading,
  concept ladder + legal pset pairing, check50-style checker reports,
  distribution (starter) code, predict-then-verify diffs, batch shelf
  preparation, hint ladder, import through the same gate, MCP server,
  hermetic test suite, packaged wheel + `cpractice-mcp` entry point.
- **Publishing runbook**: [`docs/PUBLISH.md`](docs/PUBLISH.md).
- **Engine & milestones**: [`docs/PLAN.md`](docs/PLAN.md),
  [`docs/CS50_STYLE_ENGINE_PLAN.md`](docs/CS50_STYLE_ENGINE_PLAN.md).
- **Known gap** (deliberate): public multi-user hosting stays blocked until
  the runner gets a real sandbox boundary — see SECURITY.md.

## Contributing

PRs welcome — start with [`CONTRIBUTING.md`](CONTRIBUTING.md). Ground rules in
short: tests are hermetic, the AI never appears in the grading-or-acceptance
path, hidden test content never leaves the server.

## Security

Submitting code means running untrusted C locally by design; the honest
threat model, and why public deployment stays blocked, are in
[`SECURITY.md`](SECURITY.md).

## License

[MIT](LICENSE).
