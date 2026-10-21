# Progressive hints, and when to stop giving them

Hints are optional and progressive. Each level gives away more, so the learner
can stop at the level that unblocks them without having taken the whole
answer.

## The five levels

| Level | Gives | Does not give |
|---|---|---|
| 1 | A pointer at the kind of mistake, without naming the line | The line, the fix, or the code |
| 2 | The specific concept to revisit | The fix |
| 3 | The shape of the approach, or the boundary that is being missed | The code |
| 4 | A worked fragment of the approach | The complete solution |
| 5 | The full reference solution, explicitly | - |

Level 5 is a **reveal**, and it is labelled as one. It is never the default
answer to a request for a hint.

## Rules

1. **One level per request.** Asking again moves up the ladder; it never
   returns several levels at once.
2. **The reveal is explicit.** Level 5 says plainly that it is the reference
   solution and that the learner can go back and try again.
3. **Hints target the misconception, not the syntax.** A hint that restates
   the question is wasted.
4. **A stored hint beats a generated one.** If the package already carries a
   hint for this failure mode, use it - it was written by the author, who
   knows the learners' misconceptions.
5. **Track how many hints were consumed.** The count changes what comes next:
   after several hints, the learner usually needs a *different* problem, not a
   bigger hint.

## Writing a level-1 hint that is actually useful

A level-1 hint names the *kind* of mistake and where to look, without naming
the fix:

| Failure | Weak hint | Useful level-1 hint |
|---|---|---|
| Wrong answer on one test only | "Check your loop" | "Only the boundary case fails - think about what your loop does at the last element" |
| Runtime error | "There is a bug" | "The crash happens before any output is printed - check what happens when the count is zero" |
| Timeout | "Too slow" | "The program reads its input once per loop iteration - how many times should it read?" |

The second column gives the learner nothing to act on. The third column points
at the *concept* the learner is missing, which is the thing a hint is for.

## Tying hints to declared misconceptions

When a package declares the misconceptions it is designed to surface, the hint
ladder should be written against those declarations - one level per
misconception, in the order a learner is likely to hit them:

```
misconception_id -> the hint level that addresses it
```

This keeps hints from drifting into generic encouragement, and it means the
hint ladder is auditable: every level exists because a specific wrong program
exists.

## What a hint must never do

- Never hand over a working solution when the request was for level 1-3.
- Never guess which mistake the learner made. Point at the observable failure
  and the concept, and let them decide.
- Never claim understanding on the learner's behalf. Correct the smallest
  misconception first, then ask them to restate the repaired idea.
- Never use the hint to deliver the verdict. The verdict came from the tests,
  before any hint was written.
