# ECC for OpenCode (V2 port)

ECC (agents, commands, hooks, tools, skills) for OpenCode, **ported to the
OpenCode V2 plugin API** and vendored into this project's `.opencode/` directory.

Upstream: [affaan-m/ECC](https://github.com/affaan-m/ECC) v2.2.2 (MIT).
The upstream OpenCode integration targets the **V1** plugin API, which OpenCode
V2 does not run. This directory contains a local port plus the full upstream
catalog converted to V2-native discovery.

## What is installed

| Surface | Count | Location |
| ------- | ----- | -------- |
| Agents | 68 | `.opencode/agents/*.md` |
| Commands | 108 | `.opencode/commands/*.md` |
| Skills | 339 | `.opencode/skills/<id>/SKILL.md` |
| Rules | 122 files | `.opencode/rules/` |
| Plugin + hooks | 1 plugin | `.opencode/plugins/ecc.ts` |
| Custom tools | 8 | `.opencode/tools/*.ts` |

Generated indexes:

- `.opencode/CATALOG.md` — agents, commands, and skills by category, plus a
  task→subagent routing table (`generate-catalog.mjs`).
- `.opencode/RULES.md` — reference rules by pack (`generate-rules-index.mjs`).
- `.opencode/MCP-SERVERS.md` — optional MCP servers (none enabled by default).

Counts are validated by `node .opencode/scripts/verify-vendor.mjs`.

The catalog was assembled from two ECC exports: the upstream repository (v2.2.2)
plus a secondary export (`2.0.0-rc.1`) that supplied 8 commands, 47 skills, and
the `rules/` packs. `.opencode/scripts/merge-export.mjs` performs that merge
additively — existing files always win, so the newer snapshot is never
overwritten.

## How it loads

OpenCode discovers project configuration automatically:

- `.opencode/opencode.json` — shared settings only
- `.opencode/agents/*.md` — subagents (file-based, V2 frontmatter)
- `.opencode/commands/*.md` — slash commands
- `.opencode/skills/<id>/SKILL.md` — skills
- `.opencode/plugins/*.ts` — plugins (every direct `.ts` file is loaded)

There is deliberately **no `agent`, `command`, `plugin`, or `skills` block in
`opencode.json`**: file discovery already covers them, and a JSON `command`
entry would shadow the Markdown command of the same name. Adding a `plugin`
entry would also load the plugin more than once.

The plugin default-exports a V2 plugin definition:

```ts
export default {
  id: "ecc",
  async setup(ctx) { /* register hooks, tools, transforms */ },
}
```

`Plugin.define` from `@opencode/plugin` is only an identity helper, so this port
uses a plain object and has **no runtime dependencies** — it loads even when
`node_modules` is absent (important on Termux/Android).

## Regenerating the catalog

The vendored catalog is reproducible from a pinned upstream checkout:

```bash
git clone --depth 1 https://github.com/affaan-m/ECC.git /tmp/ECC
node .opencode/scripts/vendor-upstream.mjs /tmp/ECC
node .opencode/scripts/verify-vendor.mjs
```

`vendor-upstream.mjs` converts upstream's Claude-style frontmatter to V2:

- Agents: `tools: Read, Grep, Glob` → `mode: subagent` plus `permissions`
  rules that deny `edit`/`shell` when upstream omitted Write/Edit/Bash. The
  upstream `model:` field is dropped so subagents inherit the invoking model.
- Commands: keeps `description`/`agent`/`model`/`subagent`/`subtask`; drops
  Claude-only `name`, `command`, and `argument-hint`. Existing OpenCode-specific
  command files are never overwritten.
- Skills: copied verbatim (their frontmatter is already V2-compatible).

## V1 → V2 hook mapping

| Upstream V1 hook | V2 implementation | Notes |
| ---------------- | ----------------- | ----- |
| `tool.execute.before` | `ctx.tool.hook("execute.before")` | Event shape changed (`input` is raw) |
| `tool.execute.after` | `ctx.tool.hook("execute.after")` | |
| `shell.env` | `ctx.shell.hook("create.before")` | |
| `permission.ask` | `ctx.permission.hook("evaluate")` | Sets `event.effect`; only relaxes `ask` |
| `session.created` | `ctx.event.subscribe()` | Filtered by `event.type` |
| `session.idle` | `ctx.event.subscribe()` | |
| `session.deleted` | `ctx.event.subscribe()` | |
| `file.edited` | *omitted* | No faithful V2 equivalent; tool hooks cover edits |
| `file.watcher.updated` | *omitted* | No faithful V2 equivalent |
| `todo.updated` | *omitted* | No such V2 event |
| `experimental.session.compacting` | *omitted* | V2 compaction shape differs |

Behaviour that could not be mapped faithfully is **omitted rather than silently
approximated**.

## Custom tools

Registered through `ctx.tool.transform`. All eight are available:

`run-tests`, `check-coverage`, `security-audit`, `format-code`, `lint-check`,
`git-summary`, `changed-files`, `dependency-analyzer`.

They return `{ content }` and use plain JSON Schema (V2), not the V1 `tool()`
helper. `git-summary` and any model-supplied value go through `execFileArgs`
(no shell), so there is no shell-injection surface.

## Runtime controls

```bash
export ECC_HOOK_PROFILE=standard          # minimal | standard | strict
export ECC_DISABLED_HOOKS="pre:bash:git-push-reminder,post:edit:typecheck"
```

## Sharing the catalog globally

`.opencode/` is the single source of truth. To make the agents, commands, and
skills available in **every** project, symlink them into the global OpenCode
config directory. OpenCode follows these symlinks (verified on v2.0.12).

```bash
node .opencode/scripts/link-global.mjs            # agents, commands, skills
node .opencode/scripts/link-global.mjs --plugins  # also plugin hooks
node .opencode/scripts/link-global.mjs --status   # show current state
node .opencode/scripts/link-global.mjs --remove   # unlink
opencode service restart                          # apply
```

This creates:

```text
~/.config/opencode/agents   -> <repo>/.opencode/agents
~/.config/opencode/commands -> <repo>/.opencode/commands
~/.config/opencode/skills   -> <repo>/.opencode/skills
```

Caveats:

- Links are **absolute**, so moving or deleting this repository breaks them.
  Run `--remove` before moving the repo, then re-link from the new location.
- The script never overwrites a real file or directory at the target; it skips
  and reports instead, so existing global content is preserved.
- Only `agents`, `commands`, and `skills` are linked by default. `plugins` is
  opt-in via `--plugins` because the ECC plugin registers hooks and tools that
  would then run in every project.
- OpenCode must be restarted for changes to take effect.

## Known limitations

- **~21 commands depend on Claude-only runtimes** (the `ccg-workflow` binary,
  `~/.claude/...` paths, the `ace-tool`/`jira` MCP servers). These are vendored
  for completeness but will not run correctly without those external runtimes.
  Examples: `multi-plan`, `multi-execute`, `multi-backend`, `multi-frontend`,
  `multi-workflow`, `jira`, `cost-report`, `resume-session`, `save-session`.
- **Skills add standing context.** All 292 skill descriptions are advertised to
  the model. Trim `.opencode/skills/` if sessions feel heavy, or set
  `metadata.opencode/autoinvoke: false` on skills you want loadable but hidden.
- **Instructions.** OpenCode V2 loads `AGENTS.md`, not the `instructions` config
  array. The ECC rules live at `instructions/INSTRUCTIONS.md` for reference;
  merge anything you want active into the repository `AGENTS.md`.
- **Hooks are partial** by design (see the mapping table above).

## License

MIT. Upstream ECC by [affaan-m](https://github.com/affaan-m/ECC); local OpenCode
V2 port maintained in this repository.
