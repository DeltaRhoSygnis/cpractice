/**
 * Small process helpers for the ECC plugin.
 *
 * The upstream ECC plugin used Bun's `$` shell. OpenCode runs plugins on Node
 * (and this project may run on Termux/Android where Bun is unavailable), so we
 * use `node:child_process` instead. Prefer `execFileArgs` for anything built
 * from model-supplied values (paths, refs) to avoid shell injection.
 */

import { execFile } from "node:child_process"

export interface ExecResult {
  ok: boolean
  stdout: string
  stderr: string
  code: number | null
}

export interface ExecOptions {
  cwd?: string
  signal?: AbortSignal
  timeoutMs?: number
}

/** Run an executable with an explicit argument vector (no shell). */
export function execFileArgs(
  file: string,
  args: readonly string[],
  options: ExecOptions = {}
): Promise<ExecResult> {
  return new Promise((resolve) => {
    execFile(
      file,
      [...args],
      {
        cwd: options.cwd,
        signal: options.signal,
        timeout: options.timeoutMs ?? 60_000,
        maxBuffer: 10 * 1024 * 1024,
        windowsHide: true,
      },
      (error, stdout, stderr) => {
        const code = error && typeof (error as { code?: unknown }).code === "number"
          ? ((error as { code?: number }).code ?? null)
          : error
            ? 1
            : 0
        resolve({
          ok: !error,
          stdout: String(stdout ?? ""),
          stderr: String(stderr ?? ""),
          code,
        })
      }
    )
  })
}

/**
 * Run a command line through `sh -c`.
 *
 * Only use this with trusted, static command strings. Never interpolate
 * model-supplied values here; use `execFileArgs` for those.
 */
export function sh(command: string, options: ExecOptions = {}): Promise<ExecResult> {
  return execFileArgs("sh", ["-c", command], options)
}
