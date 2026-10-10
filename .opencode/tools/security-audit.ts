/**
 * ECC custom tool: security-audit (V2 port).
 *
 * Runs security audits on dependencies and code: npm audit guidance, secret
 * scanning, and common code anti-pattern checks.
 *
 * NOTE: This tool SCANS for security anti-patterns - it does not introduce
 * them. The regex patterns below are used to DETECT potential issues.
 */

import * as path from "node:path"
import * as fs from "node:fs"
import type { ECCTool } from "./index.ts"

interface Finding {
  file: string
  issue: string
  line?: number
}

interface AuditCheck {
  name: string
  description: string
  command?: string
  severityFilter?: string
  status: "pending" | "passed" | "failed" | "warning"
  findings?: Finding[]
}

interface AuditResults {
  timestamp: string
  directory: string
  checks: AuditCheck[]
  summary: { passed: number; failed: number; warnings: number }
  recommendations?: string[]
}

export function createSecurityAuditTool(directory: string): ECCTool {
  return {
    name: "security-audit",
    description:
      "Run a comprehensive security audit including dependency vulnerabilities, secret scanning, and common security issues.",
    input: {
      type: "object",
      properties: {
        type: {
          type: "string",
          enum: ["all", "dependencies", "secrets", "code"],
          description: "Type of audit to run (default: all)",
        },
        fix: {
          type: "boolean",
          description: "Attempt to auto-fix dependency vulnerabilities (default: false)",
        },
        severity: {
          type: "string",
          enum: ["low", "moderate", "high", "critical"],
          description: "Minimum severity level to report (default: moderate)",
        },
      },
      additionalProperties: false,
    },
    async execute(input) {
      const auditType = typeof input.type === "string" ? input.type : "all"
      const fix = input.fix === true
      const severity = typeof input.severity === "string" ? input.severity : "moderate"

      const results: AuditResults = {
        timestamp: new Date().toISOString(),
        directory,
        checks: [],
        summary: { passed: 0, failed: 0, warnings: 0 },
      }

      if (auditType === "all" || auditType === "dependencies") {
        results.checks.push({
          name: "Dependency Vulnerabilities",
          description: "Check for known vulnerabilities in dependencies",
          command: fix ? "npm audit fix" : "npm audit",
          severityFilter: severity,
          status: "pending",
        })
      }

      if (auditType === "all" || auditType === "secrets") {
        const secretFindings = scanForSecrets(directory)
        if (secretFindings.length > 0) {
          results.checks.push({
            name: "Secret Detection",
            description: "Scan for hardcoded secrets and API keys",
            status: "failed",
            findings: secretFindings,
          })
          results.summary.failed++
        } else {
          results.checks.push({
            name: "Secret Detection",
            description: "Scan for hardcoded secrets and API keys",
            status: "passed",
          })
          results.summary.passed++
        }
      }

      if (auditType === "all" || auditType === "code") {
        const codeIssues = scanCodeSecurity(directory)
        if (codeIssues.length > 0) {
          results.checks.push({
            name: "Code Security",
            description: "Check for common security anti-patterns",
            status: "warning",
            findings: codeIssues,
          })
          results.summary.warnings++
        } else {
          results.checks.push({
            name: "Code Security",
            description: "Check for common security anti-patterns",
            status: "passed",
          })
          results.summary.passed++
        }
      }

      results.recommendations = generateRecommendations(results)
      return { content: JSON.stringify(results) }
    },
  }
}

function scanForSecrets(cwd: string): Finding[] {
  const findings: Finding[] = []

  // Patterns to DETECT potential secrets (security scanning).
  const secretPatterns = [
    { pattern: /api[_-]?key\s*[:=]\s*['"][^'"]{20,}['"]/gi, name: "API Key" },
    { pattern: /password\s*[:=]\s*['"][^'"]+['"]/gi, name: "Password" },
    { pattern: /secret\s*[:=]\s*['"][^'"]{10,}['"]/gi, name: "Secret" },
    { pattern: /Bearer\s+[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+/g, name: "JWT Token" },
    { pattern: /sk-[a-zA-Z0-9]{32,}/g, name: "OpenAI API Key" },
    { pattern: /ghp_[a-zA-Z0-9]{36}/g, name: "GitHub Token" },
    { pattern: /aws[_-]?secret[_-]?access[_-]?key/gi, name: "AWS Secret" },
  ]

  const ignorePatterns = ["node_modules", ".git", "dist", "build", ".env.example", ".env.template"]

  const srcDir = path.join(cwd, "src")
  if (fs.existsSync(srcDir)) {
    scanDirectory(srcDir, secretPatterns, ignorePatterns, findings)
  }

  const configFiles = ["config.js", "config.ts", "settings.js", "settings.ts"]
  for (const configFile of configFiles) {
    const filePath = path.join(cwd, configFile)
    if (fs.existsSync(filePath)) scanFile(filePath, secretPatterns, findings)
  }

  return findings
}

function scanDirectory(
  dir: string,
  patterns: Array<{ pattern: RegExp; name: string }>,
  ignorePatterns: string[],
  findings: Finding[]
): void {
  if (!fs.existsSync(dir)) return
  const entries = fs.readdirSync(dir, { withFileTypes: true })

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name)
    if (ignorePatterns.some((p) => fullPath.includes(p))) continue

    if (entry.isDirectory()) {
      scanDirectory(fullPath, patterns, ignorePatterns, findings)
    } else if (entry.isFile() && entry.name.match(/\.(ts|tsx|js|jsx|json)$/)) {
      scanFile(fullPath, patterns, findings)
    }
  }
}

function scanFile(
  filePath: string,
  patterns: Array<{ pattern: RegExp; name: string }>,
  findings: Finding[]
): void {
  try {
    const content = fs.readFileSync(filePath, "utf-8")
    const lines = content.split("\n")

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      for (const { pattern, name } of patterns) {
        pattern.lastIndex = 0
        if (pattern.test(line)) {
          findings.push({ file: filePath, issue: `Potential ${name} found`, line: i + 1 })
        }
      }
    }
  } catch {
    // Ignore read errors.
  }
}

function scanCodeSecurity(cwd: string): Finding[] {
  const findings: Finding[] = []

  // Patterns to DETECT security anti-patterns (this tool scans for issues).
  const securityPatterns = [
    { pattern: /\beval\s*\(/g, name: "eval() usage - potential code injection" },
    { pattern: /innerHTML\s*=/g, name: "innerHTML assignment - potential XSS" },
    { pattern: /dangerouslySetInnerHTML/g, name: "dangerouslySetInnerHTML - potential XSS" },
    { pattern: /document\.write/g, name: "document.write - potential XSS" },
    { pattern: /\$\{.*\}.*sql/gi, name: "Potential SQL injection" },
  ]

  const srcDir = path.join(cwd, "src")
  if (fs.existsSync(srcDir)) {
    scanDirectory(srcDir, securityPatterns, ["node_modules", ".git", "dist"], findings)
  }

  return findings
}

function generateRecommendations(results: AuditResults): string[] {
  const recommendations: string[] = []

  for (const check of results.checks) {
    if (check.status === "failed" && check.name === "Secret Detection") {
      recommendations.push("CRITICAL: Remove hardcoded secrets and use environment variables instead")
      recommendations.push("Add a .env file (gitignored) for local development")
      recommendations.push("Use a secrets manager for production deployments")
    }
    if (check.status === "warning" && check.name === "Code Security") {
      recommendations.push("Review flagged code patterns for potential security vulnerabilities")
      recommendations.push("Consider using DOMPurify for HTML sanitization")
      recommendations.push("Use parameterized queries for database operations")
    }
    if (check.status === "pending" && check.name === "Dependency Vulnerabilities") {
      recommendations.push("Run 'npm audit' to check for dependency vulnerabilities")
      recommendations.push("Consider using 'npm audit fix' to auto-fix issues")
    }
  }

  if (recommendations.length === 0) {
    recommendations.push("No critical security issues found. Continue following security best practices.")
  }
  return recommendations
}
