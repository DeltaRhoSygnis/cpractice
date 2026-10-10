#!/usr/bin/env node
/**
 * Merge a secondary ECC export into this project's .opencode/ catalog.
 *
 * The project's .opencode/ is the single source of truth. A second ECC export
 * (a differently-packaged snapshot) may add material this catalog lacks. This
 * script copies only what is missing and never overwrites an existing file, so
 * the newer of the two snapshots always wins.
 *
 * It harvests:
 *   <source>/commands/*.md   -> .opencode/commands/   (missing only)
 *   <source>/skills/<id>/    -> .opencode/skills/<id> (missing only)
 *   <source>/rules/          -> .opencode/rules/      (missing only)
 *
 * Usage:
 *   node .opencode/scripts/merge-export.mjs <path-to-other-export> [--dry-run]
 */

import * as fs from "node:fs"
import * as path from "node:path"

const args = process.argv.slice(2)
const dryRun = args.includes("--dry-run")
const sourceRoot = args.find((a) => !a.startsWith("--"))

if (!sourceRoot || !fs.existsSync(sourceRoot)) {
  console.error("Usage: node .opencode/scripts/merge-export.mjs <path-to-other-export> [--dry-run]")
  process.exit(1)
}

const opencodeDir = path.resolve(import.meta.dirname, "..")
const report = { commands: [], skills: [], rules: [], skipped: [], problems: [] }

/** Copy `src` to `dest` only if `dest` does not already exist. */
function copyIfMissing(src, dest, bucket, label) {
  if (fs.existsSync(dest)) {
    report.skipped.push(`${label}: already present`)
    return
  }
  if (!dryRun) {
    fs.mkdirSync(path.dirname(dest), { recursive: true })
    fs.cpSync(src, dest, { recursive: true })
  }
  report[bucket].push(label)
}

// --- Commands ---------------------------------------------------------------
const srcCommands = path.join(sourceRoot, "commands")
if (fs.existsSync(srcCommands)) {
  for (const file of fs.readdirSync(srcCommands).filter((f) => f.endsWith(".md"))) {
    copyIfMissing(
      path.join(srcCommands, file),
      path.join(opencodeDir, "commands", file),
      "commands",
      file
    )
  }
} else {
  report.problems.push(`no commands/ directory under ${sourceRoot}`)
}

// --- Skills -----------------------------------------------------------------
const srcSkills = path.join(sourceRoot, "skills")
if (fs.existsSync(srcSkills)) {
  for (const entry of fs.readdirSync(srcSkills, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue
    const src = path.join(srcSkills, entry.name)
    if (!fs.existsSync(path.join(src, "SKILL.md"))) continue
    copyIfMissing(src, path.join(opencodeDir, "skills", entry.name), "skills", entry.name)
  }
} else {
  report.problems.push(`no skills/ directory under ${sourceRoot}`)
}

// --- Rules ------------------------------------------------------------------
const srcRules = path.join(sourceRoot, "rules")
if (fs.existsSync(srcRules)) {
  const destRules = path.join(opencodeDir, "rules")
  // Walk recursively so nested language packs are preserved.
  const walk = (dir, rel = "") => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const src = path.join(dir, entry.name)
      const nextRel = rel ? path.join(rel, entry.name) : entry.name
      if (entry.isDirectory()) {
        walk(src, nextRel)
      } else {
        copyIfMissing(src, path.join(destRules, nextRel), "rules", nextRel)
      }
    }
  }
  walk(srcRules)
} else {
  report.problems.push(`no rules/ directory under ${sourceRoot}`)
}

console.log(JSON.stringify({
  dryRun,
  source: sourceRoot,
  commandsAdded: report.commands.length,
  skillsAdded: report.skills.length,
  rulesAdded: report.rules.length,
  skippedExisting: report.skipped.length,
  problems: report.problems,
  added: {
    commands: report.commands,
    skills: report.skills,
    rules: report.rules,
  },
}, null, 2))

if (report.problems.length > 0) process.exit(1)
