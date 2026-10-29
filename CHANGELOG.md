# Changelog

All notable changes to CPractice are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.1.0] - 2026-10-29

The first release that runs as one command and can be practised from the
browser alone.

### Added

- `cpractice` command with `start`, `doctor`, `open`, `problems`, and `version`.
  `start` reuses an instance that already answers, refuses a non-loopback bind
  without `--allow-lan`, and records its address for `open`.
- `cpractice doctor`: checks Python, home-directory writability, a real
  compile-and-run of a C program, and the port, and prints one exact fix per
  failure for Linux, macOS, Termux, and WSL2.
- Student-first dashboard: a three-fact status strip, the problem shelf, recent
  attempts, and generation behind a collapsed **Advanced** disclosure.
- One resolved home directory (`~/.cpractice` when installed, the checkout when
  running from source) that holds problems, workspaces, the SQLite history,
  `state.json`, and a fully commented `env.example`.
- Seed example packages shipped inside the package and copied once behind a
  `problems/.seeded` marker: user edits are never overwritten and deleted
  examples are never resurrected.
- Truthful grading readiness in `/api/health`: a cached compile-and-run probe
  instead of a `PATH` lookup, so a `noexec` mount cannot report green.
- `scripts/install.sh`: a guided checker that prints the exact `pipx`/`uv`
  command, installs only with `--yes`, and never pipes remote code into a shell.
- `docs/ADVANCED.md` for the HTTP API, MCP server and client configuration,
  import, generation and batch generation, provider configuration, the full
  environment reference, LAN sharing, and packaging notes.
- A wheel-contents gate (`CPRACTICE_BUILD_WHEEL=1`) that proves the built wheel
  ships the web assets and the seed packages.

### Changed

- The runtime web assets and seed packages moved inside the `app` package so an
  installed wheel can actually serve the interface.
- The README is now a learner-facing product page; developer and agent material
  moved to `docs/ADVANCED.md`, `CONTRIBUTING.md`, and `docs/PLAN.md`.
- Placeholder credentials copied from `env.example` are treated as unset, so
  copying the template cannot make the app claim AI is available.
- The test suite pins its own home directory, so running it never writes runtime
  files into the checkout.

### Fixed

- `cpractice-mcp` prints the `cpractice[mcp]` install line instead of a
  `ModuleNotFoundError` traceback when the optional SDK is absent.
- Problem statements join soft-wrapped prose into one paragraph, and fenced
  code blocks no longer render an empty first line.
- `anyio` is pinned below the `BlockingPortal` deprecation that broke collection
  on the supported test toolchain.
