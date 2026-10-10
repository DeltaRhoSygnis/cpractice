/**
 * ECC custom tool: lint-check (V2 port).
 *
 * Detects the appropriate linter and returns a runnable lint command.
 */

import * as path from "node:path"
import * as fs from "node:fs"
import type { ECCTool } from "./index.ts"

type Linter = "biome" | "eslint" | "ruff" | "pylint" | "golangci-lint"

export function createLintCheckTool(directory: string): ECCTool {
  return {
    name: "lint-check",
    description:
      "Detect linter for a target path and return command for check/fix runs. Supports cross-platform command generation.",
    input: {
      type: "object",
      properties: {
        target: {
          type: "string",
          description: "File or directory to lint (default: current directory)",
        },
        fix: {
          type: "boolean",
          description: "Enable auto-fix mode",
        },
        linter: {
          type: "string",
          enum: ["biome", "eslint", "ruff", "pylint", "golangci-lint"],
          description: "Optional linter override",
        },
      },
      additionalProperties: false,
    },
    async execute(input) {
      try {
        const target = typeof input.target === "string" ? input.target : "."
        const fix = input.fix === true
        const override = typeof input.linter === "string" ? (input.linter as Linter) : undefined
        const detected = override || detectLinter(directory)

        const command = buildLintCommand(detected, target, fix)
        return {
          content: JSON.stringify({
            success: true,
            linter: detected,
            command,
            instructions: `Run this command:\n\n${command}`,
            platform: process.platform,
            fixMode: fix,
          }),
        }
      } catch (error: unknown) {
        const errorMessage = error instanceof Error ? error.message : String(error)
        return {
          content: JSON.stringify({
            success: false,
            error: `Failed to detect linter: ${errorMessage}`,
            target: input.target,
          }),
        }
      }
    },
  }
}

function detectLinter(cwd: string): Linter {
  if (fs.existsSync(path.join(cwd, "biome.json")) || fs.existsSync(path.join(cwd, "biome.jsonc"))) {
    return "biome"
  }

  const eslintConfigs = [
    ".eslintrc.json",
    ".eslintrc.js",
    ".eslintrc.cjs",
    "eslint.config.js",
    "eslint.config.mjs",
  ]
  if (eslintConfigs.some((name) => fs.existsSync(path.join(cwd, name)))) return "eslint"

  const pyprojectPath = path.join(cwd, "pyproject.toml")
  if (fs.existsSync(pyprojectPath)) {
    try {
      const content = fs.readFileSync(pyprojectPath, "utf-8")
      if (content.includes("ruff")) return "ruff"
      if (content.includes("pylint")) return "pylint"
    } catch {
      // Ignore read errors and keep fallback logic.
    }
  }

  if (fs.existsSync(path.join(cwd, ".golangci.yml")) || fs.existsSync(path.join(cwd, ".golangci.yaml"))) {
    return "golangci-lint"
  }

  return "eslint"
}

function buildLintCommand(linter: Linter, target: string, fix: boolean): string {
  const normalizedTarget = path.normalize(target)
  const commands: Record<Linter, string> = {
    biome: `npx @biomejs/biome lint${fix ? " --write" : ""} ${normalizedTarget}`,
    eslint: `npx eslint${fix ? " --fix" : ""} ${normalizedTarget}`,
    ruff: `ruff check${fix ? " --fix" : ""} ${normalizedTarget}`,
    pylint: `pylint ${normalizedTarget}`,
    "golangci-lint": `golangci-lint run ${normalizedTarget}`,
  }
  return commands[linter]
}
