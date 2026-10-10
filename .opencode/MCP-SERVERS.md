# Optional MCP servers

Reference list of MCP servers used by the ECC exports. **Nothing here is enabled
by default.** Add the ones you actually want to the `mcp` block of
`.opencode/opencode.json`, then restart OpenCode.

Prefer the CLI so unrelated configuration is preserved:

```bash
opencode mcp add context7 -- npx -y @upstash/context7-mcp@latest
opencode mcp list
```

Remote servers use OAuth by default. If `mcp list` reports that a server needs
authentication, run `/mcps`, select the server, and sign in. Do not put API keys
in configuration; use `{env:VAR}` substitution if a header-based credential is
genuinely required.

| Server | Type | Purpose | Notes |
| ------ | ---- | ------- | ----- |
| `context7` | local | Up-to-date library/framework docs | Backs the `docs-lookup` agent and `/docs` |
| `sequential-thinking` | local | Structured multi-step reasoning | Optional |
| `memory` | local | Persistent knowledge graph memory | Optional |
| `parallel-search` | remote | Parallel web search API | Needs credentials |
| `playwright` | local | Browser automation | Backs `e2e-runner` and browser QA skills |
| `magic` | local | UI component generation | Optional |
| `filesystem` | local | Filesystem access | Example path was `/home/codespace`; adjust or omit |
| `github` | local | GitHub API operations | Backs the `github-ops` skill |
| `codegraph` | local | Code graph queries | Optional |

Configuration shape (as they appear in `opencode.json`):

```jsonc
{
  "mcp": {
    "context7": {
      "type": "local",
      "command": ["npx", "-y", "@upstash/context7-mcp@latest"]
    },
    "parallel-search": {
      "type": "remote",
      "url": "https://search.parallel.ai/mcp"
    }
  }
}
```

Some catalog entries assume an MCP server is present (for example `docs-lookup`
and `/docs` assume `context7`; `github-ops` assumes `github`). Those skills and
commands still load without it, but their external calls will fail.
