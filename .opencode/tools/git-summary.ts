/**
 * ECC custom tool: git-summary (V2 port).
 *
 * Returns branch/status/log/diff details for the active repository. Git is
 * invoked with an explicit argument vector, never a shell.
 */

import { execFileArgs } from "../plugins/lib/exec.ts"
import type { ECCTool } from "./index.ts"

// Conservative subset of git's allowed ref-name characters. Rejects shell
// metacharacters and option-like leading `-` so a model-supplied baseBranch
// cannot inject into the git command line.
const SAFE_GIT_REF = /^[A-Za-z0-9._/-]+$/

function isSafeRef(ref: string): boolean {
  if (typeof ref !== "string" || ref.length === 0 || ref.length > 200) return false
  if (!SAFE_GIT_REF.test(ref)) return false
  if (ref.startsWith("-") || ref.startsWith(".") || ref.startsWith("/")) return false
  if (ref.includes("..") || ref.includes("//")) return false
  return true
}

function isSafeDepth(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0 && value <= 1000
}

export function createGitSummaryTool(directory: string): ECCTool {
  return {
    name: "git-summary",
    description:
      "Generate git summary with branch, status, recent commits, and optional diff stats.",
    input: {
      type: "object",
      properties: {
        depth: {
          type: "number",
          description: "Number of recent commits to include (default: 5)",
        },
        includeDiff: {
          type: "boolean",
          description: "Include diff stats against base branch (default: true)",
        },
        baseBranch: {
          type: "string",
          description: "Base branch for diff comparison (default: main)",
        },
      },
      additionalProperties: false,
    },
    async execute(input) {
      const depth = isSafeDepth(input.depth) ? input.depth : 5
      const includeDiff = input.includeDiff !== false
      const baseBranch = typeof input.baseBranch === "string" ? input.baseBranch : "main"

      const result: Record<string, string> = {
        branch: (await runArgs(["branch", "--show-current"], directory)) || "unknown",
        status: (await runArgs(["status", "--short"], directory)) || "clean",
        log: (await runArgs(["log", "--oneline", `-${depth}`], directory)) || "no commits found",
      }

      if (includeDiff) {
        result.stagedDiff = (await runArgs(["diff", "--cached", "--stat"], directory)) || ""
        result.branchDiff = isSafeRef(baseBranch)
          ? (await runArgs(["diff", `${baseBranch}...HEAD`, "--stat"], directory)) ||
            `unable to diff against ${baseBranch}`
          : `unable to diff against ${baseBranch} (invalid ref)`
      }

      return { content: JSON.stringify(result) }
    },
  }
}

async function runArgs(args: string[], cwd: string): Promise<string> {
  const res = await execFileArgs("git", args, { cwd, timeoutMs: 15_000 })
  return res.ok ? res.stdout.trim() : ""
}
