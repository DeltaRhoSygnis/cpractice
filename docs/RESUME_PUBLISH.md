# Resume publish — exact runbook

State as of 2026-10-18: everything is pushed and parked; only GitHub Actions is
blocked by an **account billing lock**, not by any code failure. The identical
tree is pytest-green locally (3 expected live-provider skips).

## Current state snapshot

| Item | State |
|---|---|
| Repo | `DeltaRhoSygnis/cpractice` — **public** (flipped by owner) |
| Branch | `feat/pset-engine` pushed, head `73c6497` |
| PR | [#1](https://github.com/DeltaRhoSygnis/cpractice/pull/1) open, base `master` ← `feat/pset-engine` |
| Security checks | GitGuardian: pass |
| CI (pytest 3.12 / 3.14) | Jobs **not started** — "account is locked due to a billing issue" |
| Wheel | `cpractice-0.1.0-py3-none-any.whl` builds from the final tree (verified) |
| Push auth | HTTPS token lacks the `workflow` scope; pushes went through SSH key `cpractice-termux-publish-onetime` (id **166827052**) |

## Resume steps (after billing is settled)

1. **Rerun CI** — either rerun the failed runs or trigger a fresh one:
   ```bash
   gh run rerun <failed-run-id> --repo DeltaRhoSygnis/cpractice --failed
   # or simply watch the PR:
   gh pr checks 1 --repo DeltaRhoSygnis/cpractice --watch
   ```
2. **Fix matrix fallout if any.** Known risk: the py3.14 job installs
   requirements.txt, which pins `pydantic==2.10.4` — if cp314 wheels are
   missing for that pin, relax the pins for the 3.14 leg
   (requirements already keep `pyproject.toml` ranges as the fallback).
3. **Merge when both legs are green:**
   ```bash
   gh pr merge 1 --repo DeltaRhoSygnis/cpractice --merge
   ```
4. **Sync master and rebuild the wheel from the merged tree:**
   ```bash
   git checkout master && git pull --ff-only
   python3 -m pip wheel --no-deps --no-build-isolation -w /tmp/cp-wheel .
   ```
5. **Tag + release with the wheel artifact:**
   ```bash
   git tag v0.1.0 && git push origin v0.1.0
   gh release create v0.1.0 --repo DeltaRhoSygnis/cpractice \
     --title "v0.1.0 — first public release" \
     --notes-file <(printf '%s\n' "AI-powered C practice platform. AI generates and explains; deterministic software grades.") \
     /tmp/cp-wheel/cpractice-0.1.0-py3-none-any.whl
   ```
6. **Repository metadata:**
   ```bash
   gh repo edit DeltaRhoSygnis/cpractice \
     --description "AI-powered C programming practice with deterministic grading. AI generates and explains; deterministic software grades."
   gh repo edit DeltaRhoSygnis/cpractice \
     --add-topic c --add-topic education --add-topic programming-practice \
     --add-topic mcp --add-topic fastapi
   ```
7. **Revoke the temporary SSH key (mandatory):**
   ```bash
   gh api -X DELETE /user/keys/166827052
   ```
   Optional: also fix the underlying friction once and forever:
   `gh auth refresh -h github.com -s workflow` (one-time device code) so future
   workflow edits push over HTTPS normally.
8. **Close out:** verify the README badge renders, confirm the release shows
   the wheel, then append a one-line "published on <date>" entry to
   [PUBLISH.md](PUBLISH.md) § publication log.

Contingencies:
- If CI must be deferred again, **do not** merge unverified; the PR stays as-is
  and loses nothing.
- If a push to `feat/pset-engine` is needed before the key is deleted, use the
  same SSH invocation recorded in git history (see commit messages).
