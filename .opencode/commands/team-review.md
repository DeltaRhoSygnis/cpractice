---
description: Parallel full-team audit for existing projects. Fires code-reviewer + security-reviewer + performance-optimizer + api-guardian simultaneously. One command, complete audit at once.
subtask: true
---

# /team-review — Parallel Full-Team Code Review

Four specialist reviewers fire simultaneously for a comprehensive code review.

## What Gets Launched in Parallel

| Agent | Focus |
|---|---|
| `code-reviewer` | Code quality, readability, maintainability, patterns |
| `security-reviewer` | Vulnerabilities, injection, auth gaps, secrets |
| `performance-optimizer` | N+1 queries, bundle size, render perf, memory leaks |
| `api-guardian` | Contract correctness, data leakage, auth enforcement |

## Usage

```
/team-review                  # review uncommitted changes
/team-review src/api/         # focus on API module
/team-review --staged         # review staged changes only
```

## Report Format

```
## TEAM REVIEW REPORT

### Code Quality (code-reviewer)
ISSUES: [list with severity]
SUGGESTIONS: [list]

### Security (security-reviewer)
CRITICAL: [list]
HIGH: [list]
MEDIUM: [list]

### Performance (performance-optimizer)
BOTTLENECKS: [list]
OPTIMIZATIONS: [list]

### API Surface (api-guardian)
CONTRACT ISSUES: [list]
DATA LEAKAGE: [list]

---
RECOMMENDATION: [merge / fix-then-merge / block]
TOP 5 PRIORITIES: [ranked list]
```

## Execute Now

1. Determine scope from `$ARGUMENTS` or fall back to uncommitted changes
2. Read all changed files to build review context
3. Spawn all 4 agents simultaneously with `run_in_background: true`
4. Wait for all to complete
5. Aggregate into Team Review Report format
6. End with: "Top priorities to address before merge:"
