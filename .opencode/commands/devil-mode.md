---
description: Parallel adversarial sweep — fires prompt-injection-hunter + supply-chain-auditor + secret-hunter + backdoor-hunter simultaneously. The full attacker-mindset audit in one command.
agent: security-reviewer
subtask: true
---

# /devil-mode — Parallel Adversarial Security Sweep

Four security-focused agents fire simultaneously. What would take hours one-by-one finishes in minutes.

## What Gets Launched in Parallel

| Agent | Focus |
|---|---|
| `prompt-injection-hunter` | Prompt injection, LLM manipulation, agent jailbreaks |
| `supply-chain-auditor` | Dependency integrity, package provenance, build pipeline |
| `secret-hunter` | Hardcoded secrets, API keys, tokens, credentials |
| `backdoor-hunter` | Malicious code, data exfiltration, privilege escalation |

## Usage

```
/devil-mode                  # full repo
/devil-mode src/auth/        # focus on auth module
/devil-mode --pre-deploy     # adds environment + secrets check
```

## Report Format

```
## DEVIL MODE AUDIT REPORT

### Prompt Injection (prompt-injection-hunter)
CRITICAL: [list]
HIGH:     [list]

### Supply Chain (supply-chain-auditor)
TAMPERED: [list]
OUTDATED: [list with CVEs]

### Secrets (secret-hunter)
EXPOSED:  [list with file:line]
LEAKED:   [list in git history]

### Backdoors (backdoor-hunter)
MALICIOUS: [list]
SUSPICIOUS: [list]

---
TOTAL: X critical, Y high, Z medium
ACTION: [ship / patch first / block]
```

## Execute Now

1. Determine scope from `$ARGUMENTS`. Default: entire current project.
2. Spawn all 4 agents simultaneously with `run_in_background: true`
3. Wait for all to complete
4. Aggregate into the Devil Mode Audit Report format above
5. End with: "Which vulnerability do you want to fix first?"
