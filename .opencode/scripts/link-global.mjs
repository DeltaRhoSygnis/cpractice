#!/usr/bin/env node
/**
 * Link the project's ECC catalog into the global OpenCode config directory
 * (`~/.config/opencode/`) so the agents, commands, and skills are available in
 * every project, not just this one.
 *
 * The project's `.opencode/` stays the single source of truth (it is committed
 * and reproducible); the global side only holds symlinks.
 *
 * Usage:
 *   node .opencode/scripts/link-global.mjs              # link agents, commands, skills
 *   node .opencode/scripts/link-global.mjs --plugins    # also link plugins (hooks)
 *   node .opencode/scripts/link-global.mjs --dry-run    # show what would happen
 *   node .opencode/scripts/link-global.mjs --remove     # remove the symlinks
 *   node .opencode/scripts/link-global.mjs --status     # show current state
 *
 * Notes:
 * - Symlinks are absolute, so moving or deleting this project breaks them.
 *   Re-run with --remove first if you move the repository.
 * - OpenCode must be restarted (`opencode service restart`) for newly linked
 *   directories to be picked up.
 */

import * as fs from "node:fs"
import * as os from "node:os"
import * as path from "node:path"

const args = new Set(process.argv.slice(2))
const dryRun = args.has("--dry-run")
const remove = args.has("--remove")
const status = args.has("--status")
const includePlugins = args.has("--plugins")

const opencodeDir = path.resolve(import.meta.dirname, "..")
const globalDir = path.join(os.homedir(), ".config", "opencode")

const links = ["agents", "commands", "skills"]
if (includePlugins) links.push("plugins")

const report = { globalDir, linked: [], removed: [], skipped: [], problems: [] }

function planFor(name) {
  return { name, source: path.join(opencodeDir, name), target: path.join(globalDir, name) }
}

function describe(target) {
  try {
    const stat = fs.lstatSync(target)
    if (stat.isSymbolicLink()) return `symlink -> ${fs.readlinkSync(target)}`
    return stat.isDirectory() ? "directory" : "file"
  } catch {
    return "absent"
  }
}

if (status) {
  for (const name of links) {
    const { target } = planFor(name)
    console.log(`${name}: ${describe(target)}`)
  }
  process.exit(0)
}

fs.mkdirSync(globalDir, { recursive: true })

for (const name of links) {
  const { source, target } = planFor(name)

  if (!fs.existsSync(source)) {
    report.problems.push(`${name}: source missing at ${source}`)
    continue
  }

  if (remove) {
    try {
      const stat = fs.lstatSync(target)
      if (!stat.isSymbolicLink()) {
        report.skipped.push(`${name}: ${target} is a real directory, not a symlink; left alone`)
        continue
      }
      if (!dryRun) fs.unlinkSync(target)
      report.removed.push(`${name}: ${target}`)
    } catch {
      report.skipped.push(`${name}: nothing to remove`)
    }
    continue
  }

  // Refuse to clobber real content; a user may keep their own global files here.
  try {
    const stat = fs.lstatSync(target)
    if (!stat.isSymbolicLink()) {
      report.skipped.push(
        `${name}: ${target} already exists as a ${stat.isDirectory() ? "directory" : "file"}; move it aside first`
      )
      continue
    }
    if (fs.readlinkSync(target) === source) {
      report.skipped.push(`${name}: already linked`)
      continue
    }
    if (!dryRun) fs.unlinkSync(target)
  } catch {
    // Target absent: nothing to clear.
  }

  if (!dryRun) fs.symlinkSync(source, target)
  report.linked.push(`${name}: ${target} -> ${source}`)
}

console.log(JSON.stringify(report, null, 2))

if (remove && report.removed.length > 0 && !dryRun) {
  console.log("\nRemoved. Restart OpenCode to apply: opencode service restart")
}
if (!remove && report.linked.length > 0 && !dryRun) {
  console.log("\nLinked. Restart OpenCode to apply: opencode service restart")
}
if (report.problems.length > 0) process.exit(1)
