---
description: Parallel security audit — fires security-reviewer + dependency-doctor + api-guardian simultaneously. Full threat surface in one command.
agent: security-reviewer
subtask: true
---

# /security-audit — Parallel Security Audit

Three security-focused agents fire simultaneously. What would take an hour one-by-one finishes in 15 minutes.

## What Gets Launched in Parallel

| Agent | Focus |
|---|---|
| `security-reviewer` | OWASP Top 10, secrets in code, injection, XSS, CSRF, auth gaps, crypto misuse |
| `dependency-doctor` | CVEs in deps, outdated packages, transitive vulnerabilities, license issues |
| `api-guardian` | Exposed endpoints, missing auth, broken contracts, data leakage in responses |

## Usage

```
/security-audit                  # full repo
/security-audit src/auth/        # focus on auth module
/security-audit --pre-deploy     # adds environment + secrets check
```

## Report Format

```
## SECURITY AUDIT REPORT

### Vulnerabilities (security-reviewer)
CRITICAL: [list]
HIGH:     [list]
MEDIUM:   [list]

### Dependencies (dependency-doctor)
CVE:      [list with severity]
OUTDATED: [list]

### API Surface (api-guardian)
EXPOSED:  [list]
WARN:     [list]

---
TOTAL: X critical, Y high, Z medium
ACTION: [ship / patch first / block]
```

## When to Use

- Before any production deploy
- After adding new auth or payment flows
- When a dep audit flags CVEs
- Quarterly security health check

## Execute Now

1. Determine scope from `$ARGUMENTS`. Default: entire current project.
2. Spawn all agents simultaneously with `run_in_background: true`:
   - `security-reviewer` — full OWASP scan of codebase
   - `dependency-doctor` — CVE audit of all package manifests
   - `api-guardian` — API surface exposure check
3. Wait for all to complete
4. Aggregate into the Security Audit Report format above
5. End with: "Which vulnerability do you want to fix first?"
