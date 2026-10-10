#!/usr/bin/env node
/**
 * Generate .opencode/CATALOG.md — a compact index of the vendored ECC
 * agents, commands, and skills, plus a task→subagent routing table.
 *
 * The catalog is derived from the files on disk so it cannot drift from what
 * is actually installed. `AGENTS.md` points here; the build agent reads it
 * when choosing a subagent or skill.
 *
 * Usage: node .opencode/scripts/generate-catalog.mjs
 */

import * as fs from "node:fs"
import * as path from "node:path"

const opencodeDir = path.resolve(import.meta.dirname, "..")

function readDir(dir) {
  const full = path.join(opencodeDir, dir)
  return fs.existsSync(full) ? fs.readdirSync(full) : []
}

function firstField(text, field) {
  const match = text.match(new RegExp(`^${field}:\\s*(.+)$`, "m"))
  return match ? match[1].replace(/^["']|["']$/g, "").trim() : ""
}

function oneLine(text, max = 160) {
  const clean = text.replace(/\s+/g, " ").trim()
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean
}

// --- Agents -----------------------------------------------------------------
const agents = readDir("agents")
  .filter((f) => f.endsWith(".md"))
  .map((f) => {
    const text = fs.readFileSync(path.join(opencodeDir, "agents", f), "utf-8")
    return { id: f.replace(/\.md$/, ""), description: firstField(text, "description") }
  })
  .sort((a, b) => a.id.localeCompare(b.id))

// --- Commands ---------------------------------------------------------------
const commands = readDir("commands")
  .filter((f) => f.endsWith(".md"))
  .map((f) => {
    const text = fs.readFileSync(path.join(opencodeDir, "commands", f), "utf-8")
    return { id: f.replace(/\.md$/, ""), description: firstField(text, "description") }
  })
  .sort((a, b) => a.id.localeCompare(b.id))

// --- Skills -----------------------------------------------------------------
const skills = readDir("skills")
  .filter((name) => fs.existsSync(path.join(opencodeDir, "skills", name, "SKILL.md")))
  .map((name) => {
    const text = fs.readFileSync(path.join(opencodeDir, "skills", name, "SKILL.md"), "utf-8")
    return { id: name, description: firstField(text, "description") }
  })
  .sort((a, b) => a.id.localeCompare(b.id))

// --- Skill categorisation (heuristic, by id + description keywords) ----------
const CATEGORIES = [
  ["Testing & Quality", /test|tdd|verification|coverage|quality|review|lint|eval|regression|qa|comply|stocktake/],
  ["Security & Compliance", /security|auth|injection|secrets|bounty|compliance|hipaa|phi|privacy|risk|guard/],
  ["Architecture & Design", /architecture|pattern|design|api-|hexagonal|clean-|contract|interface|module|system/],
  ["Languages & Frameworks", /typescript|javascript|react|vue|nuxt|next|angular|svelte|python|django|flask|fastapi|golang|^go-|rust|java|spring|quarkus|kotlin|swift|swiftui|csharp|dotnet|php|laravel|ruby|rails|perl|cpp|dart|flutter|compose|node|nestjs|vite|bun|graphql/],
  ["Data, ML & Databases", /postgres|mysql|redis|prisma|jpa|hibernate|mongo|clickhouse|sql|database|migration|pytorch|ml-|mle|rag|embedding|recsys|data-|etl|warehouse/],
  ["DevOps & Infrastructure", /docker|kubernetes|deploy|ci-|cd-|git|github|gitlab|terminal|homelab|network|bgp|vlan|wireguard|dns|pihole|flox|uncloud|pm2|canary|dashboard|observability/],
  ["Agent & AI Engineering", /agent|llm|harness|loop|memory|mcp|orchestrat|council|instinct|skill-|prompt|context|subagent|tool-|autonomous|multi-model/],
  ["Docs & Process", /doc|blueprint|spec|plan|onboard|rule|adr|decision|roadmap|intent|product|workflow|session|checkpoint|learn|growth|repo-scan/],
  ["Content & Business", /market|brand|content|investor|seo|social|crosspost|email|finance|billing|logistics|inventory|customs|carrier|energy|procurement|scheduling|nonconformance|trade|outreach|lead-/],
  ["Media & Design", /video|image|media|remotion|manim|blender|taste|fal-ai|motion|design-system|ui-|frontend-slides|videodb|visa-doc/],
]

function categorise(skill) {
  const haystack = `${skill.id} ${skill.description}`.toLowerCase()
  for (const [name, re] of CATEGORIES) {
    if (re.test(haystack)) return name
  }
  return "Other"
}

const byCategory = new Map()
for (const skill of skills) {
  const category = categorise(skill)
  if (!byCategory.has(category)) byCategory.set(category, [])
  byCategory.get(category).push(skill)
}

// --- Routing table -----------------------------------------------------------
const ROUTING = [
  ["Plan a non-trivial feature or refactor", "planner, architect, code-architect, blueprint (skill)"],
  ["Explore / understand unfamiliar code", "code-explorer, code-architect, explore (builtin)"],
  ["Write tests first / drive TDD", "tdd-guide, tdd-workflow (skill)"],
  ["Review code just written", "code-reviewer, typescript-reviewer, python-reviewer, go-reviewer, rust-reviewer, java-reviewer, kotlin-reviewer, swift-reviewer, csharp-reviewer, php-reviewer, cpp-reviewer, react-reviewer, vue-reviewer, database-reviewer"],
  ["Fix a failing build / type errors", "build-error-resolver, <lang>-build-resolver (react/django/rust/go/java/kotlin/swift/pytorch/dart/cpp)"],
  ["Security review before commit", "security-reviewer, security-bounty-hunter (skill)"],
  ["Simplify / de-duplicate code", "code-simplifier, refactor-cleaner"],
  ["Find silent failures / swallowed errors", "silent-failure-hunter"],
  ["Hunt for reportable vulnerabilities", "security-bounty-hunter (skill)"],
  ["E2E / browser tests", "e2e-runner, browser-qa (skill)"],
  ["Performance work", "performance-optimizer, react-performance (skill)"],
  ["Accessibility audit", "a11y-architect, frontend-a11y (skill)"],
  ["Update docs / codemaps", "doc-updater"],
  ["Look up library/framework docs", "docs-lookup"],
  ["Run an autonomous multi-step loop", "loop-operator, continuous-agent-loop (skill)"],
  ["Evaluate agent/harness quality", "agent-evaluator, harness-optimizer, eval-harness (skill)"],
  ["Manage GitHub issues/PRs/releases", "github-ops (skill)"],
  ["Open-source a private project", "opensource-forker, opensource-sanitizer, opensource-packager"],
  ["Marketing / content / SEO", "marketing-agent, seo-specialist"],
  ["Network / homelab design", "network-architect, network-troubleshooter, network-config-reviewer"],
]

// --- Render ------------------------------------------------------------------
const lines = []
lines.push("# ECC Catalog (generated)")
lines.push("")
lines.push("> Generated by `.opencode/scripts/generate-catalog.mjs`. Do not edit by hand;")
lines.push("> re-run the script after changing the vendored catalog.")
lines.push("")
lines.push(`Contents: **${agents.length} agents**, **${commands.length} commands**, **${skills.length} skills**.`)
lines.push("")

lines.push("## Task → subagent routing")
lines.push("")
lines.push("| Task | Use |")
lines.push("| ---- | --- |")
for (const [task, use] of ROUTING) lines.push(`| ${task} | ${use} |`)
lines.push("")
lines.push("Skills are loaded by ID with the `skill` tool; subagents are launched with the")
lines.push("`subagent` tool. Prefer a specialized subagent over doing the work inline when the")
lines.push("table above matches. See AGENTS.md for the delegation rules.")
lines.push("")

lines.push("## Agents")
lines.push("")
lines.push("| Agent | Description |")
lines.push("| ----- | ----------- |")
for (const agent of agents) lines.push(`| \`${agent.id}\` | ${oneLine(agent.description, 200)} |`)
lines.push("")

lines.push("## Commands")
lines.push("")
lines.push("| Command | Description |")
lines.push("| ------- | ----------- |")
for (const command of commands) {
  lines.push(`| \`/${command.id}\` | ${oneLine(command.description || "(no description)", 160)} |`)
}
lines.push("")

lines.push("## Skills by category")
lines.push("")
for (const [category, entries] of [...byCategory.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
  lines.push(`### ${category} (${entries.length})`)
  lines.push("")
  lines.push(entries.map((s) => `\`${s.id}\``).join(", "))
  lines.push("")
}

const outPath = path.join(opencodeDir, "CATALOG.md")
fs.writeFileSync(outPath, lines.join("\n"))
console.log(
  JSON.stringify({ out: path.relative(process.cwd(), outPath), agents: agents.length, commands: commands.length, skills: skills.length }, null, 2)
)
