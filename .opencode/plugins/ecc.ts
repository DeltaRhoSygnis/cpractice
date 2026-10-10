/**
 * ECC plugin for OpenCode — V2 plugin API.
 *
 * Ported from the upstream ECC V1 plugin (`ecc-hooks.ts`), which returned a
 * hooks/tools map from a function. OpenCode V2 requires a default-exported
 * `{ id, setup(ctx) }` definition and registers hooks on their owning domain,
 * so the mapping is intentionally different:
 *
 *   V1 `file.edited`               -> not available; use the tool hooks below
 *   V1 `tool.execute.before/after` -> `ctx.tool.hook("execute.before/after")`
 *   V1 `shell.env`                 -> `ctx.shell.hook("create.before")`
 *   V1 `permission.ask`            -> `ctx.permission.hook("evaluate")`
 *   V1 `session.created/idle/deleted` -> `ctx.event.subscribe()` filtered by type
 *   V1 `todo.updated`              -> not available in V2 (omitted)
 *   V1 `experimental.session.compacting` -> not available in V2 (omitted)
 *
 * Behaviour that could not be mapped faithfully is omitted rather than
 * silently approximated; see `.opencode/README.md` for the port notes.
 *
 * This module deliberately avoids runtime imports of `@opencode/plugin` so the
 * plugin loads even when that package is not installed. `Plugin.define` is an
 * identity helper, so a plain object satisfies the runtime contract.
 */

import * as fs from "node:fs"
import * as path from "node:path"
import { execFileArgs } from "./lib/exec.ts"
import { createChangeStore } from "./lib/change-store.ts"
import { createECCTools } from "../tools/index.ts"

// ---------------------------------------------------------------------------
// Minimal structural types for the V2 plugin context surface this plugin uses.
// Keeping them local makes the plugin independent of the @opencode/plugin
// package at runtime.
// ---------------------------------------------------------------------------

interface ToolHookEvent {
  tool: string
  sessionID?: string
  id?: string
  input?: unknown
}

interface ShellHookEvent {
  command: string
  cwd: string
  env: Record<string, string | undefined>
}

interface PermissionHookEvent {
  action: string
  resources: ReadonlyArray<string>
  effect: string
  message?: string
}

interface ServerEvent {
  type: string
  [key: string]: unknown
}

interface PluginContext {
  app: { name: string; version: string; channel: string }
  location: { directory: string }
  tool: {
    transform: (cb: (editor: ToolEditor) => void) => Promise<{ dispose: () => Promise<void> }>
    hook: (name: "execute.before" | "execute.after", cb: (event: ToolHookEvent) => Promise<void> | void) => Promise<unknown>
  }
  shell: {
    hook: (name: "create.before", cb: (event: ShellHookEvent) => Promise<void> | void) => Promise<unknown>
  }
  permission: {
    hook: (name: "evaluate", cb: (event: PermissionHookEvent) => Promise<void> | void) => Promise<unknown>
  }
  event: {
    subscribe: (options?: { signal?: AbortSignal }) => AsyncIterable<ServerEvent>
  }
}

interface ToolEditor {
  add: (tool: {
    name: string
    description: string
    input: Record<string, unknown>
    execute: (input: Record<string, unknown>, context: { signal: AbortSignal; progress: (u: unknown) => Promise<void> }) => Promise<{ content: string }>
  }) => void
}

type HookProfile = "minimal" | "standard" | "strict"

const PROFILE_ORDER: Record<HookProfile, number> = { minimal: 0, standard: 1, strict: 2 }

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------

export default {
  id: "ecc",

  async setup(ctx: PluginContext) {
    const worktreePath = ctx.location.directory || process.cwd()
    const store = createChangeStore(worktreePath)

    const normalizeProfile = (value: string | undefined): HookProfile =>
      value === "minimal" || value === "strict" ? value : "standard"

    const currentProfile = normalizeProfile(process.env.ECC_HOOK_PROFILE)
    const disabledHooks = new Set(
      (process.env.ECC_DISABLED_HOOKS || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
    )

    const hookEnabled = (
      hookId: string,
      requiredProfile: HookProfile | HookProfile[] = "standard"
    ): boolean => {
      if (disabledHooks.has(hookId)) return false
      const allowed = Array.isArray(requiredProfile)
        ? requiredProfile.some((entry) => PROFILE_ORDER[currentProfile] >= PROFILE_ORDER[entry])
        : PROFILE_ORDER[currentProfile] >= PROFILE_ORDER[requiredProfile]
      return allowed
    }

    const log = (level: "info" | "warn" | "error", message: string): void => {
      const line = `[ECC] ${message}`
      if (level === "error") console.error(line)
      else if (level === "warn") console.warn(line)
      else console.log(line)
    }

    const resolvePath = (p: string): string =>
      path.isAbsolute(p) ? p : path.join(worktreePath, p)
    const hasProjectFile = (relativePath: string): boolean => {
      try {
        return fs.statSync(resolvePath(relativePath)).isFile()
      } catch {
        return false
      }
    }

    const getFilePath = (input: unknown): string | null => {
      if (!input || typeof input !== "object") return null
      const args = input as Record<string, unknown>
      const p = args.filePath ?? args.file_path ?? args.path
      return typeof p === "string" && p.trim() ? p : null
    }

    // --- Custom tools -----------------------------------------------------
    await ctx.tool.transform((editor) => {
      for (const tool of createECCTools(worktreePath, store)) {
        editor.add(tool)
      }
    })

    // --- Tool hooks (change tracking, reminders, typecheck) ---------------
    await ctx.tool.hook("execute.before", (event) => {
      if (event.tool === "write") {
        const filePath = getFilePath(event.input)
        if (filePath) {
          const type: "added" | "modified" = fs.existsSync(resolvePath(filePath))
            ? "modified"
            : "added"
          store.recordChange(filePath, type)
        }
      }

      const command = readCommand(event.input)

      if (
        hookEnabled("pre:bash:git-push-reminder", "strict") &&
        event.tool === "bash" &&
        command.includes("git push")
      ) {
        log("info", "Remember to review changes before pushing: git diff origin/main...HEAD")
      }

      if (hookEnabled("pre:write:doc-file-warning", ["standard", "strict"]) && event.tool === "write") {
        const filePath = getFilePath(event.input)
        if (
          filePath &&
          filePath.match(/\.(md|txt)$/i) &&
          !/(README|CHANGELOG|LICENSE|CONTRIBUTING)/.test(filePath)
        ) {
          log("warn", `Creating ${filePath} - consider if this documentation is necessary`)
        }
      }

      if (hookEnabled("pre:bash:long-command", "strict") && event.tool === "bash") {
        if (
          /^(npm|pnpm|yarn|bun)\s+(install|build|test|run)/.test(command) ||
          /^cargo\s+(build|test|run)/.test(command) ||
          /^go\s+(build|test|run)/.test(command)
        ) {
          log("info", "Long-running command detected - consider using background execution")
        }
      }
    })

    await ctx.tool.hook("execute.after", async (event) => {
      const filePath = getFilePath(event.input)

      if (event.tool === "edit" && filePath) {
        store.recordChange(filePath, "modified")
      }

      if (
        hookEnabled("post:edit:typecheck", "strict") &&
        event.tool === "edit" &&
        filePath &&
        filePath.match(/\.tsx?$/)
      ) {
        const result = await execFileArgs("npx", ["tsc", "--noEmit"], { cwd: worktreePath })
        if (result.ok) {
          log("info", "TypeScript check passed")
        } else {
          log("warn", "TypeScript errors detected:")
          for (const line of result.stdout.split("\n").slice(0, 5)) {
            if (line.trim()) log("warn", `  ${line}`)
          }
        }
      }

      if (
        hookEnabled("post:bash:pr-created", ["standard", "strict"]) &&
        event.tool === "bash" &&
        readCommand(event.input).includes("gh pr create")
      ) {
        log("info", "PR created - check GitHub Actions status")
      }
    })

    // --- Shell environment -------------------------------------------------
    await ctx.shell.hook("create.before", (event) => {
      const env: Record<string, string> = {
        ECC_VERSION: getECCVersion(),
        ECC_PLUGIN: "true",
        ECC_HOOK_PROFILE: currentProfile,
        ECC_DISABLED_HOOKS: process.env.ECC_DISABLED_HOOKS || "",
        PROJECT_ROOT: worktreePath,
      }

      const lockfiles: Record<string, string> = {
        "bun.lockb": "bun",
        "pnpm-lock.yaml": "pnpm",
        "yarn.lock": "yarn",
        "package-lock.json": "npm",
      }
      for (const [lockfile, pm] of Object.entries(lockfiles)) {
        if (hasProjectFile(lockfile)) {
          env.PACKAGE_MANAGER = pm
          break
        }
      }

      const langDetectors: Record<string, string> = {
        "tsconfig.json": "typescript",
        "go.mod": "go",
        "pyproject.toml": "python",
        "Cargo.toml": "rust",
        "Package.swift": "swift",
      }
      const detected: string[] = []
      for (const [file, lang] of Object.entries(langDetectors)) {
        if (hasProjectFile(file)) detected.push(lang)
      }
      if (detected.length > 0) {
        env.DETECTED_LANGUAGES = detected.join(",")
        env.PRIMARY_LANGUAGE = detected[0]
      }

      event.env = { ...event.env, ...env }
    })

    // --- Permission auto-approve ------------------------------------------
    // Only relax checks that would otherwise *ask*. An explicit `allow` or
    // `deny` from the user's configuration is never overridden, so this cannot
    // weaken a deliberate `deny` (for example on `.env` reads or `git push`).
    await ctx.permission.hook("evaluate", (event) => {
      if (event.effect !== "ask") return

      log("info", `Permission requested for: ${event.action}`)

      if (event.action === "shell") {
        const command = event.resources.join(" ")
        if (/^(npx )?(@biomejs\/biome|prettier|black|gofmt|rustfmt|swift-format)/.test(command)) {
          event.effect = "allow"
          event.message = "Formatter execution"
          return
        }
        if (/^(npm test|npx vitest|npx jest|pytest|go test|cargo test)/.test(command)) {
          event.effect = "allow"
          event.message = "Test execution"
          return
        }
      }

      // Everything else keeps asking.
    })

    // --- Session lifecycle + file changes (events) ------------------------
    const controller = new AbortController()
    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          switch (event.type) {
            case "session.created":
              if (hookEnabled("session:start")) {
                log("info", `Session started - profile=${currentProfile}`)
                if (hasProjectFile("CLAUDE.md")) {
                  log("info", "Found CLAUDE.md - loading project context")
                }
              }
              break
            case "session.idle":
              if (hookEnabled("stop:check-console-log")) {
                auditEditedFiles(store, worktreePath, log)
              }
              break
            case "session.deleted":
              if (hookEnabled("session:end-marker")) {
                log("info", "Session ended - cleaning up")
                store.clearChanges()
              }
              break
            default:
              break
          }
        }
      } catch {
        // Subscription aborted on cleanup; nothing to report.
      }
    })()

    return () => controller.abort()
  },
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function readCommand(input: unknown): string {
  if (typeof input === "string") return input
  if (input && typeof input === "object") {
    const command = (input as Record<string, unknown>).command
    if (typeof command === "string") return command
  }
  return ""
}

function getECCVersion(): string {
  try {
    const packageJsonPath = path.resolve(import.meta.dirname, "../package.json")
    const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf-8"))
    return packageJson.version || "2.0.0"
  } catch {
    return "2.0.0"
  }
}

function auditEditedFiles(
  store: ReturnType<typeof createChangeStore>,
  worktreePath: string,
  log: (level: "info" | "warn" | "error", message: string) => void
): void {
  const files = store.getChangedPaths().filter((entry) => /\.(ts|tsx|js|jsx)$/.test(entry.path))
  if (files.length === 0) return

  let total = 0
  const offenders: string[] = []
  for (const entry of files) {
    try {
      const fullPath = path.isAbsolute(entry.path)
        ? entry.path
        : path.join(worktreePath, entry.path)
      const content = fs.readFileSync(fullPath, "utf-8")
      const count = (content.match(/console\.log/g) || []).length
      if (count > 0) {
        total += count
        offenders.push(entry.path)
      }
    } catch {
      // File may have been deleted since it was recorded.
    }
  }

  if (total > 0) {
    log("warn", `Audit: ${total} console.log statement(s) in ${offenders.length} file(s)`)
    for (const file of offenders) log("warn", `  - ${file}`)
    log("warn", "Remove console.log statements before committing")
  } else {
    log("info", "Audit passed: No console.log statements found")
  }
}
