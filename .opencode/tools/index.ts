/**
 * ECC custom tools for OpenCode — shared contract.
 *
 * V2 tools are registered by the plugin through `ctx.tool.transform`, so each
 * tool is a factory that receives the active location directory (the V1
 * `context.worktree`/`context.directory` values are not part of the V2 tool
 * execution context).
 */

import type { ChangeStore } from "../plugins/lib/change-store.ts"

export interface ECCToolContext {
  signal: AbortSignal
  progress: (update: unknown) => Promise<void>
}

export interface ECCToolResult {
  content: string
}

/** A V2 tool definition (`input` is a JSON Schema object). */
export interface ECCTool {
  name: string
  description: string
  input: Record<string, unknown>
  execute: (input: Record<string, unknown>, context: ECCToolContext) => Promise<ECCToolResult>
}

export { createChangedFilesTool } from "./changed-files.ts"
export { createCheckCoverageTool } from "./check-coverage.ts"
export { createDependencyAnalyzerTool } from "./dependency-analyzer.ts"
export { createFormatCodeTool } from "./format-code.ts"
export { createGitSummaryTool } from "./git-summary.ts"
export { createLintCheckTool } from "./lint-check.ts"
export { createRunTestsTool } from "./run-tests.ts"
export { createSecurityAuditTool } from "./security-audit.ts"

import { createChangedFilesTool } from "./changed-files.ts"
import { createCheckCoverageTool } from "./check-coverage.ts"
import { createDependencyAnalyzerTool } from "./dependency-analyzer.ts"
import { createFormatCodeTool } from "./format-code.ts"
import { createGitSummaryTool } from "./git-summary.ts"
import { createLintCheckTool } from "./lint-check.ts"
import { createRunTestsTool } from "./run-tests.ts"
import { createSecurityAuditTool } from "./security-audit.ts"

/** Build every ECC tool bound to the active location directory. */
export function createECCTools(directory: string, store: ChangeStore): ECCTool[] {
  return [
    createRunTestsTool(directory),
    createCheckCoverageTool(directory),
    createSecurityAuditTool(directory),
    createFormatCodeTool(directory),
    createLintCheckTool(directory),
    createGitSummaryTool(directory),
    createChangedFilesTool(store),
    createDependencyAnalyzerTool(directory),
  ]
}
