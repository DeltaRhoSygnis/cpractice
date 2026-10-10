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
3. Create your env file and add your Google AI Studio key:

   ```bash
   cp .env.example .env
   # edit .env -> GOOGLE_API_KEY=<your key>
   ```

   In Codespaces you normally **don't** need this: the repo-scoped secret
   `GEMINI_API_KEY` is injected automatically and mapped to `GOOGLE_API_KEY`
   by the devcontainer. Secrets are only injected when the container is
   **created or rebuilt** after the secret exists — after adding a secret, run
   *Command Palette → Codespaces: Rebuild Container*.

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
| `AI_PROVIDER` | `google` (default) |
| `AI_MODEL` | Gemini model name |
| `GOOGLE_API_KEY` | Google AI Studio key (required for AI features) |
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

## Status

See [`docs/PLAN.md`](docs/PLAN.md) for the milestone checklist and current
progress.
