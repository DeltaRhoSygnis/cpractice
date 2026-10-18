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

### LAN sharing (phone hotspot / tethering) — reviewed shape

Reaching CPractice from **your own laptop** over the phone's hotspot is a
supported, reviewed configuration (`CPRACTICE_HOST=0.0.0.0 ./start.sh`,
documented in the README). What "reviewed" means here, concretely:

* The endpoint has **no authentication** — acceptance is: everyone who can
  join your hotspot is another local user who can run arbitrary C on your
  phone. Phones' hotspots usually allow this circle to be as small as you
  want (you control the pairing/clients); keep it to devices you own.
* **Do not** turn the hotspot on in a public place with the server bound to
  `0.0.0.0` and then invite others; the invite *is* remote-code-execution.
* Cellular interfaces are skipped in the `start.sh` LAN hint by design;
  binding to door number "your mobile data IP" exposes the service beyond
  the hotspot and is not covered by any review done for this repo.
* Same rules apply to the MCP server if you similarly expose
  `streamable-http`: it simply proxies submissions — the C still executes on
  the phone.

## Public / hosted deployment

The plans are explicit: **public deployment is blocked until the runner has a
real security boundary** — disposable containerised workers, no network,
restricted filesystem, resource quotas, and API secrets kept on a separate
tier (see `docs/CS50_STYLE_ENGINE_PLAN.md`, "Hosted execution"). Until that
milestone exists, do not expose CPractice to the internet from this codebase.

## Reporting

Please open a private GitHub Security Advisory rather than a public issue for
anything reachable without authentication.
