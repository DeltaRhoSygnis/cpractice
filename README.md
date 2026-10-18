# CPractice

AI-powered C programming practice platform with deterministic automated grading.

**Core principle:** AI generates and explains. Deterministic software grades.

Built from [`docs/PLAN.md`](docs/PLAN.md) (derived from the CPractice architecture
specification).

---

## What it is

A local (and later hosted) web application where you:

1. Generate or select a C programming problem.
2. Write your solution in your own editor.
3. Submit the source file and get **repeatable, deterministic** test results.
4. Request progressive hints when stuck.
5. Track attempts and practice history.

The AI is never the final authority on correctness — a validated test suite and a
trusted evaluator make that decision.

---

## Quick start (Codespace)

This repo ships a `.devcontainer` so it runs on **GitHub Codespaces**, where C
compilation and execution work without the Termux `noexec`-filesystem limitation.

1. Open the repo in a Codespace (browser or `gh codespace code`).
2. `postCreateCommand` installs dependencies and runs preflight checks.
3. Create your env file and add your AI provider key:

   ```bash
   cp .env.example .env
   # default provider is Kenari -> edit .env -> KENARI_API_KEY=<your key>
   ```

   In Codespaces the repo-scoped secret is injected automatically. Secrets are
   only delivered when the container is **created** after the secret exists;
   after adding one, recreate the codespace.

   Verify with:

   ```bash
   bash .devcontainer/setup.sh   # prints [ok]/[!] for each secret
   ```

4. Start the server:

   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

5. Open the forwarded port 8000.

---

## Quick start (local / Termux)

Termux on Android works, but **compiled binaries cannot execute on shared
storage** (`/storage/emulated/0` is mounted `noexec`). Keep the repo and all
workspaces under the Termux home directory.

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## Project layout

```text
cpractice/
├── .devcontainer/        # Codespaces definition + setup script
├── .opencode/            # project-scoped agent/skill config
├── app/                  # FastAPI application
│   ├── api/              # HTTP endpoints
│   ├── schemas/          # Pydantic problem/test/grading models
│   ├── ai/               # provider adapter interface + Google impl
│   ├── generation/       # AI generation pipeline + quality gate
│   ├── grading/          # compiler, runner, comparator, evaluator
│   ├── feedback/         # reporter + hint service
│   ├── storage/          # SQLite + repositories
│   └── services/         # application service layer
├── web/                  # plain HTML/CSS/JS frontend
├── problems/             # versioned problem packages
├── data/                 # SQLite database (gitignored)
├── workspaces/           # transient grading workspaces (gitignored)
├── tests/                # pytest suite for the platform itself
├── docs/PLAN.md          # execution plan and milestone tracking
└── requirements.txt
```

---

## Configuration

All configuration comes from environment variables (see `.env.example`).
**Never commit real secrets.** `.env` is gitignored.

| Variable | Purpose |
|---|---|
| `AI_PROVIDER` | `kenari` (default) or `google` |
| `AI_MODEL` | model id, e.g. `deepseek-v4-1-flash` |
| `KENARI_API_KEY` | Kenari gateway key (default provider) |
| `GOOGLE_API_KEY` | Google AI Studio key (used only when `AI_PROVIDER=google`) |
| `CC_COMPILER` / `CC_STANDARD` | C compiler + language standard |
| `RUN_WALL_TIMEOUT_MS` / `RUN_MEMORY_LIMIT_MB` / `RUN_MAX_OUTPUT_BYTES` | grading limits |
| `KENARI_API_KEY` | OpenCode provider key (dev tooling only) |

---

## Development

```bash
pytest                       # run the platform's own test suite
uvicorn app.main:app --reload
```

The platform's tests use **mocked AI provider responses** — no live API calls are
required to test CPractice itself.

---

## License

[MIT](LICENSE). See [`SECURITY.md`](SECURITY.md) for the (honest) threat model
around submitting code for grading, and [`CONTRIBUTING.md`](CONTRIBUTING.md)
before your first PR.

---

## Importing problem packages

Bring a problem authored elsewhere (another instance, a human, a web agent)
into CPractice with `POST /api/problems/import`. The body is one JSON document
shaped like the packages on disk — metadata at the top level plus the content
keys (`statement_md`, `starter_code`, `reference_solution`, `tests`, `hints`)
— and the same deterministic quality gate that screens AI-generated packages
runs over it. Rejected imports return the gate's findings and are **never**
written to disk; accepted ones land with `status: validated`:

```bash
curl -s -X POST http://127.0.0.1:8000/api/problems/import \
  -H 'Content-Type: application/json' \
  -d @package.json && echo
```

## MCP server (agents, Claude Desktop, opencode)

`app/mcp/` exposes the practice loop over the Model Context Protocol: the
tutor/agent can read problems, submit code to the **deterministic grader**,
walk the hint ladder, generate a problem set from your own known-concepts
checklist, import packages, and review attempts. It is a thin HTTP client over
this server (the AI never decides pass/fail; the grader's verdict is returned
verbatim).

```bash
# 1) install the optional SDK (see requirements.txt for why it is separate)
pip install "mcp==1.30.0"

# 2) start the platform, then launch the MCP server
./start.sh
python -m app.mcp.server                    # stdio (client-launched)
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

The MCP server binds to localhost and creates **no new security exposures
relative to the API itself** — see [`SECURITY.md`](SECURITY.md) before
exposing any of this beyond your own machine.

---

## Status

See [`docs/PLAN.md`](docs/PLAN.md) for the milestone checklist and current
progress.
