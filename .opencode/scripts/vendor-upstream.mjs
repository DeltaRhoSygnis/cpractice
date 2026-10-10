#!/usr/bin/env node
/**
 * Vendor the upstream ECC catalog into this project's .opencode/ directory.
 *
 * Upstream ECC keeps its agents/commands/skills in Claude Code layout
 * (`agents/*.md` with `tools:`/`model:` frontmatter). OpenCode V2 discovers
 * project agents from `.opencode/agents/*.md`, commands from
 * `.opencode/commands/*.md`, and skills from `.opencode/skills/<id>/SKILL.md`,
 * and it expresses tool access as ordered `permissions` rules.
 *
 * This script performs that conversion deterministically so the vendored copy
 * is reproducible from a pinned upstream checkout.
 *
 * Usage:
 *   node .opencode/scripts/vendor-upstream.mjs <path-to-ECC-checkout>
 *
 * It is idempotent: existing OpenCode-specific command files are preserved, and
 * generated files are overwritten in place.
 */

import * as fs from "node:fs"
import * as path from "node:path"

const upstreamRoot = process.argv[2]
if (!upstreamRoot || !fs.existsSync(upstreamRoot)) {
  console.error("Usage: node .opencode/scripts/vendor-upstream.mjs <path-to-ECC-checkout>")
  process.exit(1)
}

const projectRoot = path.resolve(import.meta.dirname, "..", "..")
const opencodeDir = path.join(projectRoot, ".opencode")

/** Parse a leading YAML frontmatter block. Returns { data, body }. */
function parseFrontmatter(text) {
  if (!text.startsWith("---")) return { data: {}, body: text }
  const end = text.indexOf("\n---", 3)
  if (end === -1) return { data: {}, body: text }
  const raw = text.slice(3, end).trim()
  const body = text.slice(end + 4).replace(/^\r?\n/, "")

  const data = {}
  for (const line of raw.split(/\r?\n/)) {
    const match = line.match(/^([A-Za-z0-9_/-]+):\s*(.*)$/)
    if (match) data[match[1]] = match[2].trim()
  }
  return { data, body }
}

/** YAML double-quoted scalar (valid for values containing ':'). */
function yamlString(value) {
  return JSON.stringify(String(value ?? ""))
}

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

// Claude tool name -> OpenCode V2 permission action.
const TOOL_TO_ACTION = {
  Write: "edit",
  Edit: "edit",
  Bash: "shell",
}

function convertAgent(name, text) {
  const { data, body } = parseFrontmatter(text)
  const tools = (data.tools || "")
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean)

  const hasWrite = tools.some((t) => t === "Write" || t === "Edit")
  const hasBash = tools.includes("Bash")

  const lines = [
    "---",
    `description: ${yamlString(data.description || name)}`,
    "mode: subagent",
  ]

  // Preserve the upstream read-only vs read-write distinction. Model is
  // intentionally omitted so subagents inherit the invoking agent's model
  // (matching upstream ECC's OpenCode guidance).
  const permissions = []
  if (!hasWrite) permissions.push({ action: "edit", resource: "*", effect: "deny" })
  if (!hasBash) permissions.push({ action: "shell", resource: "*", effect: "deny" })
  if (permissions.length > 0) {
    lines.push("permissions:")
    for (const rule of permissions) {
      lines.push(`  - action: ${rule.action}`)
      lines.push(`    resource: ${yamlString(rule.resource)}`)
      lines.push(`    effect: ${rule.effect}`)
    }
  }
  lines.push("---", "", body.trimEnd(), "")

  return lines.join("\n")
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

// OpenCode V2 command frontmatter fields; other Claude fields are dropped.
const COMMAND_FIELDS = new Set(["description", "agent", "model", "subagent", "subtask"])

function convertCommand(name, text) {
  const { data, body } = parseFrontmatter(text)

  const lines = ["---"]
  if (data.description) lines.push(`description: ${yamlString(data.description)}`)
  for (const field of ["agent", "model", "subagent", "subtask"]) {
    if (data[field]) lines.push(`${field}: ${data[field]}`)
  }
  lines.push("---", "", body.trimEnd(), "")

  // `name`/`command`/`argument-hint` are Claude-only and intentionally dropped.
  void COMMAND_FIELDS
  return lines.join("\n")
}

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

const report = { agents: 0, commands: 0, commandsSkipped: 0, skills: 0 }

// Agents: generate .opencode/agents/<name>.md for every upstream agent.
const upstreamAgents = path.join(upstreamRoot, "agents")
const agentsOut = path.join(opencodeDir, "agents")
ensureDir(agentsOut)
for (const file of fs.readdirSync(upstreamAgents).filter((f) => f.endsWith(".md"))) {
  const name = file.replace(/\.md$/, "")
  const text = fs.readFileSync(path.join(upstreamAgents, file), "utf-8")
  fs.writeFileSync(path.join(agentsOut, `${name}.md`), convertAgent(name, text))
  report.agents++
}

// Commands: add upstream commands, but never overwrite an existing
// OpenCode-specific command file (ECC ships a few that upstream lacks).
const upstreamCommands = path.join(upstreamRoot, "commands")
const commandsOut = path.join(opencodeDir, "commands")
ensureDir(commandsOut)
for (const file of fs.readdirSync(upstreamCommands).filter((f) => f.endsWith(".md"))) {
  const name = file.replace(/\.md$/, "")
  const dest = path.join(commandsOut, `${name}.md`)
  if (fs.existsSync(dest)) {
    report.commandsSkipped++
    continue
  }
  const text = fs.readFileSync(path.join(upstreamCommands, file), "utf-8")
  fs.writeFileSync(dest, convertCommand(name, text))
  report.commands++
}

// Skills: copy every skill directory verbatim (frontmatter already V2-compatible).
const upstreamSkills = path.join(upstreamRoot, "skills")
const skillsOut = path.join(opencodeDir, "skills")
ensureDir(skillsOut)
for (const entry of fs.readdirSync(upstreamSkills, { withFileTypes: true })) {
  if (!entry.isDirectory()) continue
  const src = path.join(upstreamSkills, entry.name)
  if (!fs.existsSync(path.join(src, "SKILL.md"))) continue
  fs.cpSync(src, path.join(skillsOut, entry.name), { recursive: true })
  report.skills++
}

console.log(JSON.stringify(report, null, 2))
