/**
 * ECC custom tool: run-tests (V2 port).
 *
 * Detects the package manager and test framework and returns the command to
 * run. Ported from the V1 tool; the schema is now plain JSON Schema and the
 * result is `{ content }`.
 */

import * as path from "node:path"
import * as fs from "node:fs"
import type { ECCTool } from "./index.ts"

export function createRunTestsTool(directory: string): ECCTool {
  return {
    name: "run-tests",
    description:
      "Run the test suite with optional coverage, watch mode, or specific test patterns. Automatically detects package manager (npm, pnpm, yarn, bun) and test framework.",
    input: {
      type: "object",
      properties: {
        pattern: {
          type: "string",
          description: "Test file pattern or specific test name to run",
        },
        coverage: {
          type: "boolean",
          description: "Run with coverage reporting (default: false)",
        },
        watch: {
          type: "boolean",
          description: "Run in watch mode for continuous testing (default: false)",
        },
        updateSnapshots: {
          type: "boolean",
          description: "Update Jest/Vitest snapshots (default: false)",
        },
      },
      additionalProperties: false,
    },
    async execute(input) {
      const pattern = typeof input.pattern === "string" ? input.pattern : undefined
      const coverage = input.coverage === true
      const watch = input.watch === true
      const updateSnapshots = input.updateSnapshots === true

      const packageManager = detectPackageManager(directory)
      const testFramework = detectTestFramework(directory)

      const cmd: string[] = [packageManager]
      if (packageManager === "npm") cmd.push("run", "test")
      else cmd.push("test")

      const testArgs: string[] = []
      if (coverage) testArgs.push("--coverage")
      if (watch) testArgs.push("--watch")
      if (updateSnapshots) testArgs.push("-u")
      if (pattern) {
        if (testFramework === "jest" || testFramework === "vitest") {
          testArgs.push("--testPathPattern", pattern)
        } else {
          testArgs.push(pattern)
        }
      }

      if (testArgs.length > 0) {
        if (packageManager === "npm") cmd.push("--")
        cmd.push(...testArgs)
      }

      const command = cmd.join(" ")
      return {
        content: JSON.stringify({
          command,
          packageManager,
          testFramework,
          options: {
            pattern: pattern || "all tests",
            coverage,
            watch,
            updateSnapshots,
          },
          instructions: `Run this command to execute tests:\n\n${command}`,
        }),
      }
    },
  }
}

function detectPackageManager(cwd: string): string {
  const lockFiles: Record<string, string> = {
    "bun.lockb": "bun",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "package-lock.json": "npm",
  }
  for (const [lockFile, pm] of Object.entries(lockFiles)) {
    if (fs.existsSync(path.join(cwd, lockFile))) return pm
  }
  return "npm"
}

function detectTestFramework(cwd: string): string {
  const packageJsonPath = path.join(cwd, "package.json")
  if (!fs.existsSync(packageJsonPath)) return "unknown"
  try {
    const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf-8"))
    const deps = { ...packageJson.dependencies, ...packageJson.devDependencies }
    if (deps.vitest) return "vitest"
    if (deps.jest) return "jest"
    if (deps.mocha) return "mocha"
    if (deps.ava) return "ava"
    if (deps.tap) return "tap"
  } catch {
    // Ignore parse errors and fall through to the default.
  }
  return "unknown"
}
