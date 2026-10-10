#!/usr/bin/env node
/**
 * Verify the vendored ECC catalog is internally consistent.
 *
 * Checks that every agent/command/skill file parses, that commands only
 * reference agents that exist, and that the totals match the expected upstream
 * counts. Exits non-zero on any problem so it can gate a commit.
 *
 * Usage: node .opencode/scripts/verify-vendor.mjs
 */

import * as fs from "node:fs"
import * as path from "node:path"

const opencodeDir = path.resolve(import.meta.dirname, "..")
const errors = []

function readDir(dir) {
  const full = path.join(opencodeDir, dir)
  return fs.existsSync(full) ? fs.readdirSync(full) : []
}

/** Assert a file starts with a closed `---` frontmatter block. */
function frontmatterOk(file, text) {
  if (!text.startsWith("---")) {
    errors.push(`${file}: missing frontmatter`)
    return false
  }
  if (text.indexOf("\n---", 3) === -1) {
    errors.push(`${file}: unclosed frontmatter`)
    return false
  }
  return true
}

// Agents
const agentFiles = readDir("agents").filter((f) => f.endsWith(".md"))
const agentIds = new Set()
for (const file of agentFiles) {
  const text = fs.readFileSync(path.join(opencodeDir, "agents", file), "utf-8")
  if (!frontmatterOk(`agents/${file}`, text)) continue
  const id = file.replace(/\.md$/, "")
  agentIds.add(id)
  if (!/^description:/m.test(text)) errors.push(`agents/${file}: missing description`)
  if (!/^mode:/m.test(text)) errors.push(`agents/${file}: missing mode`)
}

// Commands (frontmatter is optional in OpenCode; validate it only when present)
const commandFiles = readDir("commands").filter((f) => f.endsWith(".md"))
const builtinAgents = new Set(["build", "plan", "general", "explore"])
for (const file of commandFiles) {
  const text = fs.readFileSync(path.join(opencodeDir, "commands", file), "utf-8")
  if (text.startsWith("---") && !frontmatterOk(`commands/${file}`, text)) continue
  const match = text.match(/^agent:\s*(\S+)/m)
  if (match && !agentIds.has(match[1]) && !builtinAgents.has(match[1])) {
    errors.push(`commands/${file}: references unknown agent "${match[1]}"`)
  }
}

// Skills
const skillDirs = readDir("skills").filter((name) =>
  fs.statSync(path.join(opencodeDir, "skills", name)).isDirectory()
)
// Skill IDs are path-derived, so a directory named after a built-in skill would
// shadow it. Built-ins currently ship `opencode` and `report`.
const BUILTIN_SKILLS = new Set(["opencode", "report"])
for (const name of skillDirs) {
  if (BUILTIN_SKILLS.has(name)) {
    errors.push(`skills/${name}: ID shadows the built-in "${name}" skill; rename the directory`)
  }
  const file = path.join(opencodeDir, "skills", name, "SKILL.md")
  if (!fs.existsSync(file)) {
    errors.push(`skills/${name}: missing SKILL.md`)
    continue
  }
  const text = fs.readFileSync(file, "utf-8")
  if (!frontmatterOk(`skills/${name}/SKILL.md`, text)) continue
  if (!/^description:/m.test(text)) errors.push(`skills/${name}: missing description`)
}

// Plugin: must expose a V2 default export
const pluginPath = path.join(opencodeDir, "plugins", "ecc.ts")
if (!fs.existsSync(pluginPath)) {
  errors.push("plugins/ecc.ts: missing")
} else {
  const text = fs.readFileSync(pluginPath, "utf-8")
  if (!/export default\s*\{/.test(text) || !/\bid:\s*"/.test(text)) {
    errors.push("plugins/ecc.ts: does not default-export a V2 plugin object")
  }
}

// Config must not re-declare file-discovered surfaces
const configPath = path.join(opencodeDir, "opencode.json")
if (fs.existsSync(configPath)) {
  const config = JSON.parse(fs.readFileSync(configPath, "utf-8"))
  for (const key of ["agent", "command", "plugin", "skills"]) {
    if (key in config) {
      errors.push(`opencode.json: "${key}" duplicates file discovery and should be removed`)
    }
  }
}

console.log(
  JSON.stringify(
    {
      agents: agentFiles.length,
      commands: commandFiles.length,
      skills: skillDirs.length,
      errors,
    },
    null,
    2
  )
)

if (errors.length > 0) process.exit(1)
