---
description: "Run your question through 5 AI advisors with peer review — council this, war room this, pressure-test this"
---

# Council Command

$ARGUMENTS

## Process

### 1. Frame the question
- Scan workspace for context (CLAUDE.md, memory/, referenced files)
- Reframe the user's raw question + context into a clear, neutral prompt
- If too vague, ask one clarifying question first

### 2. Convene 5 advisors (parallel sub-agents)

Spawn all 5 simultaneously:

1. **The Contrarian** — looks for what's wrong, what will fail, fatal flaws
2. **The First Principles Thinker** — asks "what are we actually trying to solve?"
3. **The Expansionist** — looks for upside, bigger opportunity, hidden value
4. **The Outsider** — zero context, fresh eyes, catches curse of knowledge
5. **The Executor** — "what do you do Monday morning?" speed and action focus

Each advisor responds 150-300 words. No hedging. Lean fully into their angle.

### 3. Peer review (parallel sub-agents)
- Anonymize all 5 responses as Response A-E (randomized)
- Spawn 5 reviewers, each sees all 5 anonymized responses
- Each reviewer answers: strongest? biggest blind spot? what did ALL miss?

### 4. Chairman synthesis
- One agent gets everything: original question, de-anonymized responses, all peer reviews
- Produces verdict with 5 sections:
  - Where the Council Agrees (high-confidence signals)
  - Where the Council Clashes (genuine disagreements)
  - Blind Spots the Council Caught (emerged from peer review)
  - The Recommendation (clear, actionable, not "it depends")
  - The One Thing to Do First (single concrete next step)

### 5. Present verdict in chat

```
## Council Verdict: {short topic}

### Where the Council Agrees
{content}

### Where the Council Clashes
{content}

### Blind Spots the Council Caught
{content}

### The Recommendation
{content}

### The One Thing to Do First
{content}
```
