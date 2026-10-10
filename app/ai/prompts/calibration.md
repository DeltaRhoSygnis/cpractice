# Calibration — CPractice problem quality standard

This file defines what "top-level, CS50-style" means **operationally**. It is a
checklist of observable properties, not an adjective.

The reference standard is a demanding introductory computer science course:
problems that require decomposing an unfamiliar scenario, choosing an approach,
and handling several interacting requirements — not a single formula applied to
different inputs.

---

## The failure mode to avoid

A weak exercise looks like this:

```
Task: read n, print 1 + 2 + ... + n.
```
```
tests: n=1, n=5, n=100, n=0, n=100000
```

This is rejected by calibration because:

* it has **one** reasoning move (sum a range);
* every test is the same shape with different numbers;
* no test distinguishes a *wrong approach*, only wrong arithmetic;
* nothing is decomposed; the whole solution is three lines.

Difficulty varied only by input size is **not** difficulty.

---

## Required properties

### 1. Scenario specification, not a formula request

The task must be stated as a **specification to satisfy**, not a procedure to
transcribe. The learner should have to work out *what* to compute.

* Good: "Given a sequence of scores, report each score's distance from the
  running maximum seen so far."
* Weak: "Read n numbers and print the running maximum."

The second names the mechanism; the first requires deriving it.

### 2. At least two genuine reasoning moves

The solution must require at least two decisions that are not mechanical, such
as:

* derive a loop bound from a contract rather than a given count;
* maintain state across iterations;
* validate or classify input before processing;
* choose between approaches (single pass vs. two passes, counting vs. scanning);
* handle a boundary that a naive implementation gets wrong.

Exactly one reasoning move is a **warm-up**, and may only be used as a
`diagnostic_warmup` exercise role — never as a core problem.

### 3. Input that must be parsed, not just read

Reading one integer is not a skill after stage 2. Core problems should require
recognising structure in the input: multiple values, a count followed by that
many items, sentinel-terminated data, or values whose meaning depends on
position.

### 4. Tests that distinguish wrong approaches

Every listed misconception must be caught by at least one test. A test suite
where all cases are the same shape with different values fails calibration.

Required test categories (where applicable):

* minimum valid input (0 or 1 element, if the contract permits);
* maximum / near-maximum;
* the first and final valid element explicitly;
* a **misconception case** — input that a specific wrong approach gets wrong;
* an interaction case — where two requirements meet (e.g. formatting *and*
  boundary).

### 5. The statement must be complete and precise

A competent programmer must be able to implement it **without asking a
question**. State:

* exact input structure and valid domain;
* exact output format, including separators and newlines;
* what happens at boundaries and for degenerate input;
* what is guaranteed about the input (and therefore what need not be checked).

### 6. Output must carry information, not just a number

A single integer is a weak interface: it hides intermediate errors. Prefer
output that requires correct intermediate reasoning — a formatted report, a
per-element line, a classification, a reconstruction, or several derived
values.

### 7. Original and self-contained

The scenario must be invented, not a renamed textbook exercise. No reference to
course material, and no assumption that the learner has seen this exact problem
before.

---

## Exercise roles and their bars

| Role | Reasoning moves | Notes |
|---|---|---|
| `diagnostic_warmup` | 1 | May be simple; this is the only role allowed to be |
| `core_reasoning` | 2+ | The standard. Must require deriving, not transcribing |
| `transfer` | 2+ | Same skill, materially different scenario |
| `challenge` | 3+ | May combine previously practised concepts |
| `debugging` | — | Supplies faulty code; learner finds the counterexample |
| `reflection` | — | Asks why it works, or predicts behaviour |

A unit of practice should be mostly `core_reasoning`. Warm-ups do not
accumulate: a stream of single-move exercises is the failure mode.

---

## Calibration questions

Answer these about a candidate problem. **Any "no" on `core_reasoning` or above
is a rejection.**

1. Does the learner have to work out **what** to compute, rather than being told?
2. Are there at least two **non-mechanical** reasoning moves?
3. Does the input have **structure** that must be recognised?
4. Does at least one test **distinguish a wrong approach**, not merely wrong arithmetic?
5. Could a competent programmer implement this **without asking a question**?
6. Does the output expose **intermediate** correctness?
7. Is the scenario **original** rather than a renamed standard exercise?
8. Would a learner who solves a dozen of these become better at **unfamiliar**
   problems?

Question 8 is the purpose of the whole exercise. If the honest answer is no,
the problem is failing regardless of how correct its tests are.
