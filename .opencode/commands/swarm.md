---
description: Spawn N specialist agents in parallel inside isolated git worktrees + a tmux session. Generalized /devil-mode for any task + agent combination.
subtask: true
---

# /swarm — Parallel Multi-Agent Execution

Spawn multiple specialist agents in parallel, each working in an isolated git worktree.

## Usage

```
/swarm <task description> [--agents agent1,agent2,...] [--harness claude|codex|opencode|windsurf]
```

## What It Does

1. **Parse** — Extract task, agent list, and harness from `$ARGUMENTS`
2. **Plan** — Decompose task into non-overlapping subtasks
3. **Isolate** — Create a git worktree per agent
4. **Dispatch** — Launch agents in parallel via tmux
5. **Monitor** — Track progress across all worktrees
6. **Merge** — Integrate completed worktrees back to main

## Agent Selection

Default specialist roster (adjust based on task type):

| Task Type | Agents |
|-----------|--------|
| Feature build | fullstack-developer, frontend-developer, backend-developer |
| Security audit | security-reviewer, backdoor-hunter, api-guardian |
| Code quality | code-reviewer, refactor-cleaner, tdd-guide |
| Infrastructure | devops-engineer, database-reviewer |
| Debugging | debug-detective, env-debugger, flake-hunter |

## Execution Model

- Each agent gets its own git worktree under `.swarm/`
- Agents cannot see each other's changes until merge
- Main session monitors via tmux session `swarm-{task-id}`
- Completed worktrees are merged sequentially to avoid conflicts

## Output

```
SWARM RESULT: [SUCCESS / PARTIAL / FAILED]

Agents:
  agent-1: [SUCCESS/FAILED] — [summary]
  agent-2: [SUCCESS/FAILED] — [summary]

Worktrees merged: [list]
Conflicts: [none / list with resolution]
```
