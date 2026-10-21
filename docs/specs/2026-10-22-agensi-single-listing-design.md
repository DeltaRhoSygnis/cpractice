# Agensi.io — Single-Listing Funnel Design

**Document type:** Design specification
**Date:** 2026-10-22
**Status:** Approved for planning
**Origin:** Agensi.io creator-acquisition email (`agensi.txt`), product-positioning
analysis (`docs/agensi/FEASIBILITY.md`, prior session `ses_ea0446597ffeKC851f0QfVj3Us`)
**Supersedes:** the six-listing plan in `docs/agensi/FEASIBILITY.md` §4

---

## [S1] Problem

Agensi.io is a marketplace for standalone `SKILL.md` packages that install into
Claude Code, Cursor, Codex, Copilot, Gemini CLI and ~20 other agents. We were
asked to list our work there. The platform is real and the format is
well-documented, but three facts decide what is worth building:

1. **The marketplace does not sell education.** The Education/Teaching category
   is saturated with zero-install listings at $5–$49 ("Personal AI Coding Tutor"
   $9.99 → 0 installs; "Coding Teacher — Bundle" $39 → 0 installs).
2. **The long tail is the whole marketplace.** 12,994 live listings; the median
   listing has approximately 0 installs. Free generic utilities own the top of
   the install chart (`code-reviewer` 1,794 installs). The 65,000 monthly
   visitors the outreach email cites are *site* traffic, not buyers.
3. **Nobody is asking for what we know.** The request board has one public
   request (a fulfilled $10 receipt-finder bounty). Searches for `autograd`,
   `competitive programming` and `C programming` return zero listings — but the
   absence of competitors is equally the absence of evidence of demand.

The prior session produced six packages, six logos and six listing packets. That
was supply-side work answering a question that was never asked. It also produced
one genuinely useful conclusion — **"AI never decides pass/fail"** — and one
demonstrably bad call: that the four thin tutor skills (`code-review` at 51
words, `debugging` at 55, `retrieval` at 47, `examination` at 168) were our
fastest revenue, because they compete on the most saturated keywords on the
site with bodies that are behaviour nudges, not skills.

**Therefore the question is not "what do we list?" It is "what is the one
artifact worth building, who is the buyer, and what happens after they click?"**

---

## [S2] Solution overview

Publish **exactly one** Agensi listing — a single bundled skill package at
**$9 one-time** — designed as the top of a funnel that ends at CPractice, not
as a revenue product.

Three decisions follow from it:

| Decision | Rationale |
|---|---|
| **One SKU, not six** | Every additional listing multiplies review-queue risk, cold-start surface and copy work against a marketplace where the median listing earns nothing. The education category sells nothing; more listings is not more revenue. |
| **$9 one-time, not free, not a bundle, not a subscription** | A price filters browsers and produces real buyer questions — our cheapest demand probe. Free maximises installs from curiosity and tells us nothing. A subscription we cannot service from a funnel is a support liability. |
| **The listing's job is to make a stranger trust the repo** | The only asset with genuine pull is the public CPractice repository and its README. The listing is the proof artifact that travels in email, on Reddit, and in Discord — where instructors actually are. |

**The reframe that makes it sell to teachers.** The prior session pitched the
verdict taxonomy as internal engineering. To an instructor it is *gradebook
semantics*: a pass/fail grader cannot award partial credit, and cannot tell a
student "your loop was correct, your off-by-one on the last case was not".
That is the seven-category outcome model (`compile error / passed / wrong
answer / runtime error / timeout / output limit exceeded / internal error`), and
it is a problem every course owner already has.

---

## [S3] The package

One skill directory, one ZIP, one listing.

```
deterministic-autograder/
├── SKILL.md                        # router + three condensed procedures
├── README.md                       # buyer-facing: what it does, how to use it
└── references/
    ├── result-taxonomy.md          # verdict model + result schema
    ├── mutation-operators.md       # C-specific operators, killed/survived table
    ├── c-edge-cases.md             # edge-case catalogue for student programs
    ├── problem-package-schema.md   # the problem-package contract
    └── hint-ladder.md              # progressive hints, level-5 reveal
```

**Why this shape dodges the format risk.** Their format reference warns that a
2,000-word multi-topic skill underperforms four focused 500-word ones. Our
`SKILL.md` is therefore a **router, not an encyclopedia**: a short procedure per
competency, with an explicit "read `references/<file>.md` for the detail" line
at each one. Depth lives in `references/`, which is also the "$12–25
comprehensive package" shape their pricing guide rewards ("skills with
supporting materials sell for 2–3× more and get better reviews"). A bundle *is*
a multi-topic skill — the site already sells bundles at $39 — so this is a
proven format, not a gamble.

**Content provenance** (maintainer map — *not* shipped inside the ZIP, since
the ZIP must contain no repo paths):

| Reference | Distilled from |
|---|---|
| `result-taxonomy.md` | `app/schemas/grading.py`, `app/grading/evaluator.py` |
| `mutation-operators.md` | `app/generation/mutation.py` |
| `c-edge-cases.md` | `app/generation/blueprint.py`, `app/generation/calibration.py`, and the `problems/` packages |
| `problem-package-schema.md` | `app/schemas/problem.py`, `app/schemas/test_case.py` |
| `hint-ladder.md` | `app/feedback/hint_service.py`, `app/generation/misconceptions.py` |

**Naming and packaging constraints** (each one is a silent failure or a
rejection if broken):

- Folder name `deterministic-autograder`; frontmatter `name` must equal it
  exactly, lowercase and hyphenated. A mismatch means the skill never loads.
- `description` is the activation trigger: one to three sentences, written as
  "Use when the user asks to…", with 3–5 trigger phrases.
- ZIP contains exactly one top-level folder with `SKILL.md` at its root.
- Text files only — no binaries, no symlinks, no OS cruft.
- No repo paths, no internal URLs, no provider names, no secrets inside the ZIP.
  The call-to-action link lives in the *listing description*, outside the archive.
- Body must define an explicit output format and explicit "do not do this"
  boundaries; it must not read as a prompt override.

**Scanner discipline.** Their 8-point security scan rejects "dangerous
commands" and "executing remote code". Our material is about compiling and
running student submissions, which is exactly the shape that trips a naive
scanner. Mitigation, non-negotiable:

- The body states **design guidance** — "specify a sandbox this way", "separate
  these outcomes" — and never emits a literal shell invocation of user source.
- **No `scripts/` directory.** References and prose only. A shipped script that
  compiles and runs code is a scan risk we do not need to take.
- No `rm -rf`, no process killing, no network access, no environment access.
- Declared permissions on the listing: no terminal, no writes, no network, no
  environment variables; read-only file scopes. An advisory skill that talks
  about running code while declaring no terminal access is the shape the
  scanner should like.

---

## [S4] Listing copy and the demo

Their upload form has a field they call **"the single biggest conversion
driver on your listing"**: Step 3, *See it in action* — one realistic request
prompt plus a complete, never-truncated result of 700+ characters. The result
is the product.

**The request (what a buyer types):**

> "I'm setting up an autograder for my introductory C course. Students submit
> source, I need per-test verdicts and partial credit, and I need to be sure my
> hidden tests actually catch wrong answers. How should I specify this?"

**The result (the complete deliverable the agent produces):** a single coherent
output containing —

1. the verdict model (the outcome categories and the result schema), with the
   partial-credit rule;
2. the rule that no AI or heuristic may author a verdict;
3. a discriminating-test plan: which mutation operators to apply to a reference
   solution, what a survivor means, and how to strengthen the suite;
4. the edge-case checklist to walk before writing hidden tests;
5. the hint ladder shape for a struggling student.

Structure: short summary → verdict table → discriminating-test table →
checklist → next steps. One request, one deliverable, no truncation.

**Remaining form fields** — name (≤60 chars), one-line summary, full
description, compatibility note, price ($9, one-time), tags/categories/use
cases, permissions block with the audit note, FAQ, documentation link, logo
(512×512 square), screenshots, demo video URL.

Reusable assets already on disk: `docs/agensi/listings/*/listing.md` field
transcriptions, `docs/agensi/logos/` (generated by `make-logos.py`),
`docs/agensi/build-zips.sh` (which already refuses to package a skill whose
frontmatter `name` ≠ folder name). These are edited, not rewritten from zero.

---

## [S5] Funnel and landing surface

**Destination.** The CTA lands on the CPractice case study in the portfolio —
canonical `https://jessiejamesportfolio.vercel.app/projects/cpractice/`
(mirrored at `https://deltarhosygnis.github.io/portfolio/projects/cpractice/`).
`bryllim.com` is a *reference* site whose layout was adapted earlier; it is
not ours and must never appear as a link.

**Flow:**

```
[Agensi listing $9]  ──▶  portfolio CPractice case study  ──▶  github.com/DeltaRhoSygnis/cpractice
[outreach email]     ──▶  the same page
```

**The case study page gains an instructor path** — five additions:

1. **Who it's for**, above the fold: an instructor running a C course. Not
   buried in a paragraph about mutation testing.
2. **Classroom workflow in three lines:** generate a problem set → students
   submit → per-test verdicts and partial credit → attempt history and a hint
   ladder.
3. **One-command install and the no-API-key path.** This is the real conversion
   blocker and it is a *product* gap, not a copy problem: the repository today
   requires `./start.sh`, a `.env` file and an AI provider key. Hand-authored
   problem packages must be gradeable with **zero** API keys, because an
   instructor is not a developer and will not configure one.
4. **A deterministic verdict demo** — compile error → pass → wrong answer →
   timeout — visible in ten seconds without installing anything.
5. **Interest capture** — an explicit "using this with your class? email me"
   with an instructor-specific address. The portfolio already has a copy-email
   affordance; this points it at the right audience.

**Why the landing page matters more than the listing.** The marketplace hands
us, at best, a handful of installs. The page is what converts an install into a
teacher. Everything about the copy, the demo, and the one-command path exists
to make that click worth something.

---

## [S6] Instrumentation and success criteria

GitHub Pages serves no access logs, and UTM funnels cannot be measured there.
The funnel is therefore measured by three signals, in descending order of
reliability:

1. **The interest email.** The only genuine conversion event. Everything else
   is a proxy for it.
2. **Agensi Creator Studio** analytics: views → carts → installs → reviews.
3. **GitHub repository traffic API** (clones, unique cloners, referrers) — a
   step change around submission and around each outreach wave.

Additionally: enable the Vercel Analytics script on the portfolio (the tag is
already present but commented out in `index.html`) so case-study page views and
referrers are visible. Referrers will tell us whether Agensi sent anyone.

**Decision rule at 90 days after publication:**

| Outcome | Action |
|---|---|
| ≥ 50 installs **and** ≥ 10 case-study visits, or ≥ 3 instructor emails | Channel works — build the demo video, add the second listing, keep investing |
| Installs but no instructor interest | The skill lands, the audience does not — keep the listing as a portfolio artifact, stop investing, redirect effort to direct outreach |
| Neither | Agensi is a dead traffic channel for us. Keep the listing live and free of maintenance; do not rebuild it. |

**Budget:** roughly 3–4 days of work across the package rewrite, the landing
page, the demo recording and distribution. **Expected marketplace revenue:
$0–$70/month, most likely $0.** The return is a packaged, public statement of
the one thing we know that nobody else has written down, and a priced artifact
to hand an instructor in an email.

---

## [S7] Execution sequence

Sequenced by what unblocks what, and by the KYC gate on paid listings.

| # | Task | Output | Gate |
|---|---|---|---|
| 1 | Rewrite `SKILL.md` in router form; write the five references; write `README.md` | `docs/agensi/skills/deterministic-autograder/` | Format checklist |
| 2 | Update `build-zips.sh` for the new package; build and verify structure | `docs/agensi/dist/deterministic-autograder.zip` | `name` == folder name |
| 3 | Rewrite the listing copy: name, summary, description, one complete demo, FAQ, permissions, tags | `docs/agensi/listings/deterministic-autograder/listing.md` | Demo ≥700 chars, untruncated |
| 4 | Extend the portfolio case study with the instructor path; enable Vercel Analytics | portfolio repo change | One-command install works; zero-key path works |
| 5 | Implement the **no-API-key grading path** in CPractice (product gap that gates task 4's promise) | CPractice change | Hand-authored package grades with no key set |
| 6 | Record one 30–45s screen recording of an agent using the skill end-to-end; cut screenshots from it | demo video + screenshots | Their guide: a 30s video doubles conversion |
| 7 | Submit the listing | — | 24–48h review |
| 8 | Complete KYC (payment method already connected — confirm KYC status, which is the actual gate on a *paid* listing) | — | Blocks publication of a paid skill |
| 9 | Publish; then one build-in-public post and the instructor outreach list | — | — |

Tasks 5 and 4 are ordered deliberately: promising a zero-key path before it
exists would be the one lie the funnel cannot afford.

---

## [S8] Risks and mitigations

| Risk | Mitigation |
|---|---|
| Scanner rejects the package for "dangerous commands" | Design-guidance framing, no `scripts/`, no shell invocations, declare no terminal/network/env permissions. Their scan is re-run on resubmit and there is no penalty for failing. |
| KYC blocks the paid listing | Verify KYC status *before* writing the copy — a payment method is not KYC. If KYC stalls, fall back to the free companion (see S9). |
| Zero demand — the empty category means no demand, not an opportunity | The 90-day decision rule in S6 caps the loss at roughly four days of work. |
| The audience mismatch is fatal: Agensi buyers are agent-tool buyers, instructors are not | Accepted, and priced in: the listing is a leave-behind for direct outreach, and marketplace installs are a bonus channel, not the plan. |
| Stale skill — rules encode knowledge that can be wrong | Version against CPractice releases; their platform pushes updates to every buyer free, which is a reason to post and a distribution event. |
| Support load | Declare the support method on the listing; answer only buyer questions; time-box. A $9 buyer with a bug is not a customer relationship. |
| Duplicate listing by a competitor | Non-exclusive by contract. The moat is iteration speed and depth of the quality rules, not the file. |

---

## [S9] Explicitly out of scope

- **The four tutor skills** (`code-review`, `debugging`, `examination`,
  `retrieval`) stay in the repository and are **not** listed. They are 47–168
  word behaviour nudges on the site's most saturated keywords; listing them
  buys zero-install noise and spends review-queue credibility.
- **A second listing.** The taxonomy can be split out of the same ZIP into a
  free companion (`deterministic-grading-contract`, ~300 words) later without
  rebuilding anything — that is the option we preserve by keeping the
  references separable. It is the fallback if KYC stalls.
- **A formal Agensi bundle.** Their April guide says new creators have no
  formal bundle pricing while the site shows $39 bundles — a contradiction to
  resolve in the dashboard, not a plan to build on now.
- **A hosted CPractice instance.** It is the real product gap for instructor
  adoption, but it is a separate project with its own security boundary
  (hosted execution requires stronger sandboxing than the local runner).
- **A full outreach program.** Task 9 lists it; the list, cadence and templates
  are a separate design.

---

## [S10] Decisions taken, for the record

1. Goal: **funnel into CPractice**, not marketplace revenue.
2. Mechanism: **one listing that serves both discovery and outreach** — the
   same artifact is the search surface and the leave-behind.
3. Landing: **the existing portfolio case study**, extended with an instructor path.
4. SKU count: **one**.
5. Price: **$9, one-time**.
6. Package shape: `SKILL.md` router + five references + `README.md`, no scripts.
7. The listing's promise is only truthful once the **no-API-key path exists**.
