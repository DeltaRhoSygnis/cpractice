---
description: GAN harness loop — brain agent orchestrates planner→generator→evaluator iterations with auto-commit.
subtask: false
---

# /gan-loop — GAN Harness Brain

Orchestrate the full GAN-style build loop. This command runs in the current
session and delegates each phase to the `gan-planner`, `gan-generator`, and
`gan-evaluator` subagents.

## Usage

```
/gan-loop <brief description> [--max-iterations N] [--pass-threshold N]
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--max-iterations` | 15 | Maximum generator-evaluator cycles |
| `--pass-threshold` | 7.0 | Weighted score to pass |

## What It Does

1. Analyzes scope from your brief
2. Delegates planning to `gan-planner`
3. Runs `gan-generator` ↔ `gan-evaluator` loop
4. Monitors score progression
5. Auto-commits after each sub-agent
6. Reports final build report

## Example

```
/gan-loop Build a project management app with Kanban boards and dark mode
```
