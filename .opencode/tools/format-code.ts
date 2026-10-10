/**
 * ECC custom tool: format-code (V2 port).
 *
 * Detects the formatter for a file and returns the exact command to run.
 */

import * as path from "node:path"
import * as fs from "node:fs"
import type { ECCTool } from "./index.ts"

type Formatter = "biome" | "prettier" | "black" | "gofmt" | "rustfmt" | "swift-format"

export function createFormatCodeTool(directory: string): ECCTool {
  return {
    name: "format-code",
    description:
      "Detect formatter for a file and return the exact command to run (Biome, Prettier, Black, gofmt, rustfmt, swift-format). Supports cross-platform command generation.",
    input: {
      type: "object",
      properties: {
        filePath: {
          type: "string",
          description: "Path to the file to format",
        },
        formatter: {
          type: "string",
          enum: ["biome", "prettier", "black", "gofmt", "rustfmt", "swift-format"],
          description: "Optional formatter override",
        },
      },
      required: ["filePath"],
      additionalProperties: false,
    },
    async execute(input) {
      try {
        const filePath = String(input.filePath ?? "")
        const override = typeof input.formatter === "string" ? (input.formatter as Formatter) : undefined
        const ext = filePath.split(".").pop()?.toLowerCase() || ""
        const detected = override || detectFormatter(directory, ext)

        if (!detected) {
          return {
            content: JSON.stringify({
              success: false,
              message: `No formatter detected for .${ext} files`,
              supportedFormatters: ["biome", "prettier", "black", "gofmt", "rustfmt", "swift-format"],
            }),
          }
        }

        const command = buildFormatterCommand(detected, filePath)
        return {
          content: JSON.stringify({
            success: true,
            formatter: detected,
            command,
            instructions: `Run this command:\n\n${command}`,
            platform: process.platform,
          }),
        }
      } catch (error: unknown) {
        const errorMessage = error instanceof Error ? error.message : String(error)
        return {
          content: JSON.stringify({
            success: false,
            error: `Failed to detect formatter: ${errorMessage}`,
            filePath: input.filePath,
          }),
        }
      }
    },
  }
}

function detectFormatter(cwd: string, ext: string): Formatter | null {
  const hasConfig = (configFiles: string[]): boolean =>
    configFiles.some((configFile) => fs.existsSync(path.join(cwd, configFile)))

  if (["ts", "tsx", "js", "jsx", "json", "css", "scss", "md", "yaml", "yml"].includes(ext)) {
    if (hasConfig(["biome.json", "biome.jsonc"])) return "biome"
    return "prettier"
  }
  if (["py", "pyi"].includes(ext)) return "black"
  if (ext === "go") return "gofmt"
  if (ext === "rs") return "rustfmt"
  if (ext === "swift") return "swift-format"
  return null
}

function buildFormatterCommand(formatter: Formatter, filePath: string): string {
  // Normalize to forward slashes so the emitted command is identical on every
  // platform; all formatter CLIs accept `/` on Windows.
  const normalizedPath = path.normalize(filePath).replace(/\\/g, "/")

  const commands: Record<Formatter, string> = {
    biome: `npx @biomejs/biome format --write ${normalizedPath}`,
    prettier: `npx prettier --write ${normalizedPath}`,
    black: `black ${normalizedPath}`,
    gofmt: `gofmt -w ${normalizedPath}`,
    rustfmt: `rustfmt ${normalizedPath}`,
    "swift-format": `swift-format format --in-place ${normalizedPath}`,
  }
  return commands[formatter]
}
