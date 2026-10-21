# Resume publish — exact runbook

State as of 2026-10-21: **the code is merged into `master`.** What remains is
the **release**, and it is deliberately held until GitHub Actions can actually
run. The blocker is an **account billing lock**, not any code failure.

## Current state snapshot

| Item | State |
|---|---|
| Repo | `DeltaRhoSygnis/cpractice` — **public** |
| `master` | `99259cb` — **PR #1 merged** (merge tree identical to branch head `ca65647`) |
| Branch `feat/pset-engine` | `ca65647` — merged, still on the remote |
| PR | [#1](https://github.com/DeltaRhoSygnis/cpractice/pull/1) — **MERGED** 2026-10-21T02:30:59Z |
| Local suite on the merged tree | **753 passed, 3 skipped, 0 failed** (3 skips = expected live-provider skips) |
| `v0.1.0` tag / GitHub Release | **HELD** — not created yet, by design |
| Wheel | `cpractice-0.1.0-py3-none-any.whl` builds from the final tree (verified) |
| CI (pytest 3.12 / 3.14) | Jobs **not started** — "account is locked due to a billing issue" |
| Branch protection | **none** on `master`; no repository rulesets |
| SSH deploy key `166827052` | **revoked** (2026-10-21). Pushes of `.github/workflows/*` now need `gh auth refresh -s workflow` |

## Why the merge did not wait for CI

`master` was never branch-protected and the repo has no rulesets, so the
billing-locked jobs were not a merge gate — `gh pr merge 1 --merge` was
available immediately and produced a clean, conflict-free merge.

The **release** is the thing that deserves CI, because the published wheel is
what users install. It is held until the canonical toolchain validates the
tree. This device is Termux/Android + **clang 21** + Python 3.14; CI is
ubuntu-latest + **gcc** + Python 3.12/3.14. The grading engine shells out to
the local C compiler, so *which* compiler is real.

## Resume steps (after billing is settled)

1. **Rerun CI** — either rerun the failed runs or trigger a fresh one:
   ```bash
   gh run rerun <failed-run-id> --repo DeltaRhoSygnis/cpractice --failed
   # or simply watch the runs on master:
   gh run watch --repo DeltaRhoSygnis/cpractice
   ```
2. **Fix matrix fallout if any.** Known risk: the py3.14 job installs
   requirements.txt, which pins `pydantic==2.10.4` — if cp314 wheels are
   missing for that pin, relax the pins for the 3.14 leg
   (requirements already keep `pyproject.toml` ranges as the fallback).
3. **Rebuild the wheel from the merged tree:**
   ```bash
   git checkout master && git pull --ff-only
   python3 -m pip wheel --no-deps --no-build-isolation -w /tmp/cp-wheel .
   ```
4. **Tag + release with the wheel artifact:**
   ```bash
   git tag v0.1.0 && git push origin v0.1.0
   gh release create v0.1.0 --repo DeltaRhoSygnis/cpractice \
     --title "v0.1.0 — first public release" \
     --notes-file <(printf '%s\n' "AI-powered C practice platform. AI generates and explains; deterministic software grades.") \
     /tmp/cp-wheel/cpractice-0.1.0-py3-none-any.whl
   ```
   Note: tagging/pushing is fine over the current HTTPS token, but if the
   release needs a **workflow-file** change, run
   `gh auth refresh -h github.com -s workflow` first (the one-time SSH deploy
   key has been revoked).
5. **Repository metadata:**
   ```bash
   gh repo edit DeltaRhoSygnis/cpractice \
     --description "AI-powered C programming practice with deterministic grading. AI generates and explains; deterministic software grades."
   gh repo edit DeltaRhoSygnis/cpractice \
     --add-topic c --add-topic education --add-topic programming-practice \
     --add-topic mcp --add-topic fastapi
   ```
6. **Close out:** verify the README badge renders, confirm the release shows
   the wheel, then append a one-line "published on <date>" entry to
   [PUBLISH.md](PUBLISH.md) § publication log.

## Optional cleanups (not blocking)

- `feat/pset-engine` is fully merged and can be deleted from the remote:
  `git push origin --delete feat/pset-engine`.
- Local `feat/pset-engine` can be removed too: `git branch -d feat/pset-engine`.

Contingencies:

- If CI must be deferred again, **do not** release unverified; `master` already
  holds the verified-locally tree, and a release costs nothing to defer.
- If the py3.12 leg fails on something Android-specific, that is exactly the
  signal CI was meant to catch — fix it on `master` and release after.
