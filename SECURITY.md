# Security policy

## Honest threat model

CPractice compiles and **executes C binaries supplied by whoever submits**.
Everything in the default local configuration is tuned for *one trusted user
on one machine*, and only that. Read this before letting anyone else near it.

### What the local runner does protect against

* runaway programs (wall-clock timeout, CPU-time limit via `RLIMIT_CPU`),
* output floods (`RUN_MAX_OUTPUT_BYTES`),
* periodic per-problem memory limits (best effort, platform-dependent),
* transient grading state (dedicated, isolated workspaces under
  `workspaces/`).

### What it deliberately does NOT protect against

The runner is **not a security boundary against deliberately malicious code**
(this is stated in `app/grading/runner.py`, `docs/PLAN.md`, and
`docs/CS50_STYLE_ENGINE_PLAN.md`). Specific gaps a local setup accepts on
purpose:

* **No authentication.** Anyone who can reach the port can submit code.
* **No network/device isolation.** Submitted programs run as *your user* with
  your filesystem permissions.
* **No sandbox.** There is no seccomp/containerisation on the grading path.
* **`/api/problems/import` writes packages to disk** after validation — do not
  let untrusted clients call it.

### Rules that keep the default configuration safe

1. Bind to `127.0.0.1` only. Never `0.0.0.0` without a security review
   (flagged in `.env.example`).
2. One user, one machine, trusted content. That is the supported shape.
3. The **MCP server binds to localhost** and is a thin client over the same
   API; everyone in the MCP trust chain can run arbitrary C locally. Do not
   plug untrusted agents into it.

## Public / hosted deployment

The plans are explicit: **public deployment is blocked until the runner has a
real security boundary** — disposable containerised workers, no network,
restricted filesystem, resource quotas, and API secrets kept on a separate
tier (see `docs/CS50_STYLE_ENGINE_PLAN.md`, "Hosted execution"). Until that
milestone exists, do not expose CPractice to the internet from this codebase.

## Reporting

Please open a private GitHub Security Advisory rather than a public issue for
anything reachable without authentication.
