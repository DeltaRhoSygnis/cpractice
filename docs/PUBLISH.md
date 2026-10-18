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

This repo **already lives on GitHub**: `DeltaRhoSygnis/cpractice`, **private**,
default branch `master` (1,325 `.opencode/` files already tracked; audit of
that same history in §1 is clean of real secrets). "Publishing" therefore
means **flipping visibility to public**, not creating a new repo — and the
history that exists today becomes public exactly as it is.

`.opencode/` (~13 MB) is the vendored agent toolkit including personal-ish
skill prose (e.g. `brand-discovery`). It is development harness, not product.

| Option | Effect | Note |
|---|---|---|
| **A. Ship history as-is** | zero further work; phase out `.opencode/` in a later commit | simplest; 13 MB stays in clone cost |
| **B. Untrack going forward, keep history** | `git rm -r --cached .opencode && echo ".opencode/" >> .gitignore && git commit` | clones still download the old blobs, but the working tree is clean |
| **C. Rewrite history before the flip (safest story)** | new clean `master` (squash), force-push, then flip private→public | only safe **while the repo is private** (no outside clones exist) — exactly the situation now |

If C is chosen, prefer `git commit-tree`/`filter-repo` against a fresh branch
and verify the audit of the *new* history; then `git push --force origin
master`.

## 3. Publication flow on the existing repo

1. Push the feature branch and open the PR:
   `git push -u origin feat/pset-engine` → PR `feat/pset-engine` → `master`
2. Resolve the uncommitted engine WIP first (commit, or deliberately keep out
   — but know that CI tests the pushed tree only).
3. In the PR, decide `master`'s 2 unpushed commits and the `.opencode/` call
   from §2.
4. CI must be green on both matrix entries (py3.12 pinned stack py3.14
   floats). The MCP SDK is optional by design; CI never requires it.
5. Merge, then flip `gh repo edit --visibility public` (only after the
   `.opencode/` decision), then complete §4.

## 3. Pre-publish verification (run again on the branch that will be merged)

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
