# Publishing checklist (go-open-source runbook)

Everything in this repo is already **written for publication** (MIT LICENSE,
SECURITY.md, CONTRIBUTING.md, CI, importable wheel). What remains is decisions
and by-hand steps that must not be automated away. Work top to bottom: each
step ends in an observable state.

---

## 1. Recorded-by-hand audit results (2026-10-18)

**Secret scan of full git history** (`git log --all -p`) — every match is a
deliberately-fake test fixture, quoted here so nobody re-audits in panic:

| Match in history | Verdict |
|---|---|
| `kenari_api_key="kn-should-never-appear"` | test asserting non-leak |
| `"kn-super-secret-value"` / `google-key-present` | mock fixtures |
| `JWT_SECRET=change-me-to-a-random-string` | template text |
| `password: mySecretPassword123` | inside `brand-discovery` skill prose |

No `ken-…`/`kn-…`-style real gateway key, no Google key, no password material
in history. `.env` has never been tracked (`git ls-files` confirms;
`.env.example` contains placeholders only).

**Re-run the scan the day you publish** — it costs one command:

```bash
git log --all -p \
  | grep -nIiE "(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}" \
  | grep -viE "example|placeholder|your[_-]|never-appear|super-secret|present-but|mock"
# expect: no output
```

## 2. The `.opencode/` decision — **the one open call**

`.opencode/` is ~13 MB / 1,325 **tracked** files: the vendored agent toolkit
(prompts, skills, rules — including `brand-discovery` and its personal
references). It is your development harness, **not the product**.

| Option | Effect | Note |
|---|---|---|
| **A. Ship it** | cost: 13 MB noise in a public repo, personal material exposed | not recommended |
| **B. Untrack going forward** | `git rm -r --cached .opencode && echo ".opencode/" >> .gitignore` | files remain in *history* until the history is squashed |
| **C. Publish from a squashed clean history (recommended)** | public `main` starts at a single commit containing product + docs + tests; keep this working branch private as backup | nothing personal, no toolkit, simplest forensic story |

Recommended flow (option C):

```bash
# 1) opinions-free copy of what should be public
git checkout feat/pset-engine
git rm -r --cached .opencode            # toolkit stays on disk, leaves the index
echo ".opencode/" >> .gitignore
git commit -m "chore: stop tracking the private agent toolkit"

# 2) publish tree only
work=$(mktemp -d)
git archive HEAD | tar -x -C "$work"
cd "$work"
# review: git status is trivially clean; ls -la shows no .opencode, no notes.txt
```

`git archive` never carries ignored/untracked files (`notes.txt`,
`_archive/`, `.env`, `data/`, `workspaces/`, `problems/` generated content are
excluded by the same rule), and never carries history — the squashed history
is created by pushing this tree as a fresh initial commit:

```bash
cd "$work" && git init -b main && git add -A
git commit -m "CPractice 0.1.0: AI-assisted C practice with deterministic grading"
git remote add origin git@github.com:<you>/cpractice.git
git push -u origin main
```

Development continues on your private repo; public repo is an export point per
release (re-run the checklist each time).

## 3. Pre-publish verification (run again on the export tree)

```bash
python -m pip install -r requirements.txt   # core stack
python -m pip wheel --no-deps -w dist .     # wheel builds; prompts + entry point included
python -m pytest -q                          # full suite green (~3 live-API skips are expected)
./start.sh                                   # health 200
python -m app.mcp.server --help               # MCP console script entry point exists
```

GitHub Actions must be green on both matrix entries (py3.12 pinned, py3.14).
The MCP SDK is optional by design; CI never requires it.

## 4. Publication cosmetics

1. Fill the repository URL into `[project.urls]` in `pyproject.toml`
   (currently left empty on purpose).
2. Repo description: *"AI-powered C programming practice with deterministic
   grading. AI generates and explains; deterministic software grades."*
3. Topics: `c`, `education`, `programming-practice`, `static-analysis`,
   `mcp`, `fastapi`.
4. Settings → Security: GitHub should auto-detect `SECURITY.md`; enable
   private vulnerability reporting.
5. Tag: `git tag -a v0.1.0 -m "first public release"` and cut a GitHub Release
   with the wheel as artifact.

## 5. What must never enter the public tree

- `.env` (any real key — Kenari/Google), `data/`, `workspaces/`,
  generated `problems/` beyond the two tracked fixtures,
  `notes.txt`, `_archive/`, `.opencode/`.
- If a real key ever lands there by accident: **rotate the key first**,
  clean the history second — order matters.

## 6. Known-declared gaps for the public 0.1.0

- No authentication; grading runner is not a sandbox
  (`SECURITY.md` documents both; public/web deployment stays blocked until a
  containerised boundary exists — the "T3" milestone).
- `app/services/problem_import.py` mirrors
  `GenerationPipeline.save` until both converge behind a shared writer
  (deliberate, to avoid entangling the in-flight pset-engine branch).
