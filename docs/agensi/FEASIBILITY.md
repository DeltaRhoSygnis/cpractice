# Agensi.io — Asset Assessment & Listing Plan

Status: draft, uncommitted. Sources: `agensi.txt`, the live site
(`agensi.io/sell`, `agensi.io/learn/skill-md-format-reference`,
`agensi.io/learn/skill-md-creator-checklist`, `agensi.io/learn/how-agensi-security-scan-works`),
and a read-only query of the public marketplace catalogue (12,994 live listings
as of 2026-10-22).

## 1. What Agensi actually sells

A marketplace for **standalone `SKILL.md` packages** that install into Claude
Code, Cursor, Codex, Copilot, Gemini CLI, Windsurf, Aider, Cline, Zed, Kiro,
OpenClaw, and ~10 more, plus distribution through the Agensi MCP connector
(`mcp.agensi.io`). The package format is:

```
my-skill/
├── SKILL.md          # required
├── references/       # optional docs the agent can read
├── scripts/          # optional executable helpers
├── assets/           # optional templates
└── README.md         # optional but strongly recommended
```

### Commercial terms (verified on /sell)

| Item | Value |
|---|---|
| Listing fee | None — free to list |
| Platform fee | 30% flat, all-in (no per-sale flat fee) |
| Creator share | 70% of net |
| Payout | Stripe, or USDC on Solana (Zoneless) |
| KYC | Required before a *paid* skill can go live |
| Payout timing | Queued for the next payout cycle after payment clears |
| Listing types | One-time purchase, or monthly subscription (can stack both) |
| Extras | Deals/discounts per skill, bundles, creator profile, followers, versioned updates with approval history, Creator Studio funnel analytics (views → carts → conversions → installs → reviews) |
| Review | 8-point automated security scan → AI review of safety and intent → human review. Usually 24–48h |
| Taxes/refunds | Agensi is the seller of record; you never register for tax in buyers' countries |

**Bundle pricing precedent on the live site:** "Coding Teacher — Bundle" $39,
"Code Explainer — Bundle" $39, "Kids Homework Helper — Bundle" $39. Bundles are
a proven format here and are the natural home for a set of related tutor skills.

### The format spec (verified on /learn/skill-md-format-reference)

- **Required frontmatter:** `name` and `description`. Everything else optional.
- `name` must equal the **parent folder name** exactly — lowercase, digits and
  hyphens only. A mismatch means the skill silently fails to load.
- `description` is the single most important field: it decides activation.
  One to three sentences. Sentence one = what it does. Sentence two = when to
  use it, with trigger phrases. Multiple phrasings of the same intent are
  encouraged.
- Optional fields: `when_to_use`, `argument-hint`, `arguments`,
  `allowed-tools`, `context: fork`, `model`, `effort`,
  `disable-model-invocation`, `hooks`. Agent-specific; silently ignored
  elsewhere, but note in the description if you rely on them.
- Body = markdown instructions, organised with headers, numbered procedures,
  examples, explicit output format, and explicit "do not do this" boundaries.
- The spec explicitly warns: a 2,000-word skill covering four topics will
  underperform four separate 500-word skills. **Split is the default.**

### The creator checklist (verified on /learn/skill-md-creator-checklist)

- Description should be written as "Use when the user asks to…" with 3–5
  trigger phrases.
- Body must define an **output format** — without it, agents produce
  inconsistent results.
- **At least one supporting file** (reference doc, script, or example).
- A `README.md` in the skill folder "significantly improves buyer confidence".
- Scripts must only operate inside the project directory, no elevated
  permissions, no package installs, no system config changes, and be
  well-commented so buyers can audit them.
- **Zip structure:** exactly one top-level folder named after the skill, with
  `SKILL.md` at that folder's root. Not at the zip root, not double-nested.
- Text files only — no binaries, no symlinks, no `.DS_Store`/`Thumbs.db`.
- Test in at least two agents before publishing, and have someone who did not
  write it install and try it.
- "Skills with supporting materials sell for significantly more and get better
  reviews." A separate guide states supporting files sell for **2–3× more**.

### The 8-point security scan (verified on /learn/how-agensi-security-scan-works)

1. Prompt injection
2. Data exfiltration (sending user data out, reading outside project scope,
   touching secret env vars)
3. Dangerous commands (recursive deletes, system config changes, unknown
   package installs, executing remote code)
4. Hardcoded secrets (keys, tokens, passwords)
5. Obfuscated code (base64, minified)
6. Suspicious network access (runtime fetches, downloaded scripts)
7. Zip structure integrity
8. SKILL.md validity (parseable YAML frontmatter, non-empty body)

The scan gives a specific explanation of what failed and re-runs on resubmit;
there is no penalty for failing. Every live listing shows a "Security scanned"
badge, and that badge is the differentiator against unvetted SKILL.md files on
GitHub — so it is worth passing first time.

**Consequence for our skills:** the two drafts talk about compiling and
executing submitted code, killing processes, and enforcing resource limits.
That reads as "dangerous commands" to an automated scanner unless it is framed
as *guidance the agent writes*, not commands the agent runs. Keep the skill
body at the level of "design your grader like this" and never emit a literal
`rm -rf` or a shell invocation of user source.

## 2. Market reality check

The site advertises "12,000+ Skills, 12,000+ Users, 1,500+ Creators". The
catalogue query shows **12,994 live listings**. Actual distribution is extremely
long-tailed:

| Rank | Skill | Installs | Views | Price |
|---|---|---|---|---|
| 1 | code-reviewer | 1,794 | 11,775 | free |
| 2 | humanize-writing | 734 | 2,746 | free |
| 3 | prompt-engineer | 557 | 2,715 | free |
| 4 | git-commit-writer | 476 | 3,259 | free |
| 5 | readme-generator | 344 | 1,983 | free |
| 6 | codex-grade-coding | 298 | 1,489 | free |
| 7 | skill-creator | 258 | 1,301 | free |
| — | Prompt Dataset Builder | 162 | 503 | $9.90 |
| — | Online Course Builder | 23 | — | $49 |
| — | Educational worksheet pack builder | 0 | — | $5 |
| — | Coding Teacher — Bundle | 0 | — | $39 |

Read this carefully before planning revenue:

- **Free skills own the top of the install chart.** The five most-installed
  skills are all free and all generic utilities.
- **Conversion is what moves views to installs**: `code-reviewer` converts
  11,775 views → 1,794 installs (~15%). `Prompt Dataset Builder` does 503
  views → 162 installs (~32%) at $9.90 — paid, and the best-converting paid
  listing in the top 100.
- **The median listing has ~0 installs.** The Education and Teaching
  categories are saturated with 0-install listings at $5–$49: "Educational
  worksheet pack builder" ($5, 0), "Teacher Lesson Plan Generator" (free, 0),
  "Professional curriculum and lesson plan builder" ($5, 0), "Assessment
  Rubric Designer" ($9.99, 0), "Personal AI Coding Tutor" ($9.99, 0), "Quiz
  assessment builder" ($5, 0), "Pedagogical Simulation Matrix" ($29, 0).
- **The email's "65,000 monthly visitors" is site traffic, not buyers.** The
  traffic lands on a marketplace where 12,994 skills compete for the same
  clicks.

**The strategic implication:** the bottleneck is *discovery and proof*, not
packaging. A listing that nobody finds is worth $0 regardless of how good the
skill is. Two things actually produce installs on this site: (a) being a
generic, high-frequency utility that people search for by name, and (b) a
listing that proves its value — demo video, before/after, or a screenshot.
The site explicitly says creators who post the workflow, or a 30–60s screen
recording, sell 2–3× more.

So our two flagship skills are **not** a fast-money play; they are a
differentiated, low-volume play in a category with a genuine gap. The tutor
set is the same story. The realistic model is: a small catalogue that ranks,
plus own-channel distribution, not passive marketplace income.

## 3. Competitive gap

Queries run against the live catalogue: `grad`, `judge`, `exercise`, `problem`,
`tutor`, `pedagog`, `curricul`, `autograd`, `competitive programming`, `hint`,
`teach`, `c programming`.

- **`autograd` → 0 results. `competitive programming` → 0 results.** No listing
  covers deterministic grading of programming exercises.
- The nearest neighbours are all about *LLM* evaluation, not *code*:
  "AI Eval & Test Suite Quality Gate" ($14), "AI Feature Eval Writer" ($24),
  "Agent Quality Judge" ($9.99), "LLM Judge Bias Calibrator" ($15),
  "EvalForge — Mechanical Eval Gates for Agents" (free).
- "Personal AI Coding Tutor" ($9.99, 0 installs) and "Socratic Code Reviewer"
  (free, 18) are the closest to our tutor set — both near-zero traction.
- **Zero C-programming-specific skills** in the catalogue.

Two conclusions:

1. **Whitespace is real, demand is unproven.** Nothing competes with a
   deterministic autograder skill because nobody has built one, not because
   people are buying them.
2. **The tutor set is a commodity.** "Personal AI Coding Tutor" already exists
   at $9.99 with zero installs. Our four tutor skills are *better written* but
   compete on the same keyword. Their advantage is that they are a coherent
   set — which is exactly what a **bundle** is for, and bundles at $39 have a
   live precedent.

## 4. Recommended listing plan

Pricing follows the marketplace's own guide (verified on
`/learn/how-to-price-skill-md-skills`): **$3–$9 for single-purpose skills,
$12–$25 for comprehensive ones** (SKILL.md + reference files + scripts +
README). A bare SKILL.md is worth $3–$5; a package with supporting material is
worth $12–$25. $5 is the named sweet spot for single-purpose skills.

The same guide's advice for a new creator: **publish one or two free skills
first**, get to 50+ installs, then launch paid ones. And note: "Agensi doesn't
have formal bundle pricing yet" (April 2026 guide) — but the live site has
`/bundles` and a "Coding Teacher — Bundle" at $39. **Verify in the dashboard
before planning around bundles.** The safe default is individual listings with
cross-links in the descriptions, which the guide says drives higher attachment
rates anyway.

**Tier 1 — two free tutor listings, two $5 tutor listings.**

| Listing | Price | Why |
|---|---|---|
| `code-review` | **Free** | Code review is the #1 selling category on Agensi. Free = installs = credibility. |
| `debugging` | **Free** | Second of the free pair, per the guide's "one or two free first". |
| `examination` | **$5** | Single-purpose, $5 sweet spot. |
| `retrieval` | **$5** | Single-purpose, $5 sweet spot. |

**Tier 2 — the two flagships, both with `references/` + README (the $12–$25
comprehensive band).**

| Listing | Price | Why |
|---|---|---|
| `deterministic-code-grader` | **$15** | Comprehensive; the outcome taxonomy and report schema are the parts a buyer would otherwise build. |
| `exercise-authoring` | **$12** | Comprehensive; teacher audience is more price-sensitive. |

**Tier 3 — optional.** `progressive-hinting` from the feedback engine, $5–$9.
Only if Tier 1 and 2 land.

**Demand caveat, checked directly:** the skill request board
(`agensi.io/requests`) currently lists **one** public request (a fulfilled
$10 bounty on "Receipt Finder & Organizer"). There is no waiting buyer for an
autograder skill, and no waiting buyer for a tutor skill. The board is not a
channel yet. Their own guide's demand check — "search the query your skill
would answer" — is the test to run before spending more time here.

### What the marketplace's own guide says does *not* sell

Quoting their "what sells best" article, because it is uncomfortable and
useful:

> "Ultra-niche skills for very specific libraries or frameworks with tiny
> user bases... won't get enough traffic to generate meaningful sales
> regardless of quality."

and

> "Skills that duplicate what the agent already does well... the value
> proposition has to be clear."

Our position: a deterministic-grading skill is a *narrow* skill, but the
category is empty and the buyer (anyone building a judge) has a real,
expensive problem — which is a better position than a niche with a *crowded*
category. The tutor skills are the opposite risk: broad audience, crowded
category, generic-sounding value. Which is why they are the free tier.

### Package status (built 2026-10-22)

All six skill packages exist under `skills/` and build cleanly:

| Package | Body | Supporting files | Zip |
|---|---|---|---|
| `code-review` | 35 words | README | ✔ |
| `debugging` | 41 words | README | ✔ |
| `examination` | 155 words | README | ✔ |
| `retrieval` | 34 words | README | ✔ |
| `deterministic-code-grader` | ~1,900 words | README + `references/result-taxonomy.md` | ✔ |
| `exercise-authoring` | ~1,870 words | README + `references/edge-case-catalogue.md` | ✔ |

`./build-zips.sh` produces `dist/<name>.zip` with the required structure: one
top-level folder named after the skill, `SKILL.md` at its root, text files
only, no OS cruft. The script also refuses to build a package whose frontmatter
`name` does not match its folder — the one mistake that makes a skill fail
silently.

The four tutor packages are intentionally terse (34–155 words). That is
correct: the format spec says focused, small skills outperform long
multi-topic ones, and the whole point of these four is one behaviour each.

The two flagships are **over the length the spec recommends** (~1,900 words
against a suggested ~800). Two options, and the second is probably better:

- **Split.** `deterministic-code-grader` → *outcome model & taxonomy* +
  *sandboxing & limits*. `exercise-authoring` → *test design & coverage* +
  *pedagogy: difficulty, misconceptions, hints*. Four focused listings
  instead of two, each with its own price and its own search surface.
- **Trim.** Cut each body to ~800 words, keep the depth in `references/`, and
  let the agent read the reference when it needs it. Lower risk, one listing
  per topic, but a thinner listing card.

**Do not submit either as-is.** Both currently bundle four topics each, which
is exactly the failure mode the format guide calls out.

## 5. The submission form (from `skill_upload.txt`)

The actual upload form tells us what a listing needs, and it changes the
priority order. Required fields: **ZIP, Skill Name, Summary, Full
Description, Pricing Model, Price**.

| Step | Field | Note |
|---|---|---|
| 1 | Skill ZIP | 50 MB max. Fields auto-populate from frontmatter. |
| 2 | Skill logo | Square, 512×512, 5 MB max. Not marked required, but "listings with a logo and at least one screenshot get noticeably more installs". |
| 2 | Skill Name | Max 60 chars, or it gets cut on cards. |
| 2 | Summary | One line. |
| 2 | Full Description | Markdown. |
| 3 | **Demo** | "The single biggest conversion driver on your listing." Two fields: *the request* (a realistic prompt) and *the result* (complete, never truncated, 700+ characters, structured). |
| 4 | Compatibility Note | |
| 5 | Pricing | Free / One-time / Subscription. Minimum $1. |
| 5 | Tags, Categories, Use cases | Recommended. |
| 5 | **Permissions** | Recommended, and auto-detected from the ZIP. Tools used, required software, file scopes (globs), and a note explaining why. |
| 6 | FAQ, Screenshots (max 6), Demo video URL, Documentation link | Recommended. "A 30-second demo video doubles conversion." |

**Three consequences:**

1. **The Step 3 demo is the listing.** It is explicitly the biggest
   conversion driver, and it costs nothing but writing. Every listing
   packet in `listings/` has a complete, non-truncated demo result.
2. **The Permissions block is a trust signal we should use, not dodge.** Our
   skills are advisory: they declare *no* terminal, no writes, no network, no
   env vars. The two tutor skills that read a file declare read-only globs.
   A skill that talks about compiling and running code but declares no
   terminal access is exactly the shape the security scanner should like.
3. **The logo and the demo video are the two things we cannot write.** A
   512×512 square mark and a 30-second screen recording are the remaining
   blockers for a real launch, and they are hours of work, not days.

### Assets ready (2026-10-22)

| Asset | Status |
|---|---|
| 6 skill ZIPs | ✔ built, structure verified |
| 6 logos | ✔ 512×512 PNG, generated by `make-logos.py` |
| 6 full listing packets | ✔ `listings/<skill>/listing.md`, every form field filled |
| 6 demo sections | ✔ complete, non-truncated, 1.5k–4.4k characters each |
| FAQ + permissions blocks | ✔ for all six |
| Demo video (30s) | ✘ **outstanding** |
| Screenshots | ✘ outstanding (the Step 3 demo substitutes for now) |
| Stripe + KYC | ✘ outstanding, and it blocks the paid listings going live |
| Documentation link | ✘ outstanding |

`listings/<skill>/listing.md` is a transcription of the upload form, field by
field, so it can be pasted straight into the form. Everything in it is
copy-ready except the two items marked outstanding.

### Pre-submission checklist (per listing)

- [ ] `name` == folder name, lowercase-hyphen only
- [ ] `description` written as "Use when the user asks to…" with 3–5 trigger phrases
- [ ] Body has numbered procedures, at least one example, an explicit output format, and explicit boundaries
- [ ] Body under ~800 words; depth moved to `references/`
- [ ] At least one supporting file in `references/` or `examples/`
- [ ] `README.md` in the folder
- [ ] Zip = one top-level folder, `SKILL.md` at its root
- [ ] No binaries, no symlinks, no `.DS_Store`
- [ ] No secrets, no repo paths, no provider names, no internal URLs
- [ ] Nothing in the body that reads as a dangerous command or as a prompt override
- [ ] Tested in Claude Code + one other agent; tested by someone who did not write it
- [ ] Payouts connected + KYC done **before** the paid skill goes live
- [ ] Demo video or before/after capture prepared (this is what actually moves installs)

## 6. The reply to Joeri, and what actually drives installs

**On whether replying is worth it — the honest answer is that it is not worth
much, and the plan must not depend on it.** The reasoning:

- Joeri is doing creator acquisition, not curation. He sourced you from a
  list; he is not the person who reviews listings and is unlikely to have
  bandwidth to read two skill drafts. Asking him to validate the content is
  asking a stranger for a favour, on a cold email, with no leverage.
- His reply cannot create demand. The demand-side facts are fixed: 12,994
  live listings, a median of ~0 installs, an empty request board, and a
  traffic figure (65k visitors) that lands on a marketplace, not on our
  listing.
- The two questions worth asking are mechanical, not editorial: does formal
  bundle pricing exist for a new creator (the guide says no, the site shows
  bundles), and what category/tag placement fits a deterministic-grading
  skill. Both are answerable in the dashboard, the docs, or
  `info@agensi.io`.

So the reply is now a **four-line heads-up that states what is being
submitted and asks only the two mechanical questions** — no validation
request, no long pitch. If he never answers it, nothing is blocked. If he
does, it may return a contact, a category hint, or a bundle answer.

**What actually drives installs**, from their own playbook:

1. **The listing's demo section.** Explicitly the single biggest conversion
   driver, and it is already written for all six listings.
2. **A 30-second demo video.** "Doubles conversion." This is the one
   non-text asset we owe.
3. **A logo and at least one screenshot.** "Noticeably more installs."
4. **Own-channel posts showing the workflow, not the pitch** — the messy
   manual task, then the agent doing it, with the link. Their data says
   creators who do this sell 2–3× more. Reddit, X, LinkedIn, dev.to, and
   Discord are named.
5. **One build-in-public write-up** explaining the problem the skill solves.
   A single post keeps sending buyers for months.
6. **A free first listing** to seed installs, then paid ones with the
   credibility behind them.

Distribution is the product here. The listing is the storefront.

## 7. Risks
- **Distribution is the product.** A perfect skill with no promotion earns
  roughly what the median listing earns: nothing. Budget for own-channel
  posts, a demo recording, and a build-in-public write-up.
- **Long-tail reality.** Median installs on a 13k-listing marketplace are near
  zero. Model this as portfolio income, not a side hustle replacing a salary.
- **Education category is saturated** with cheap, zero-install listings.
  Differentiation has to be in the *proof*, not the price.
- **Stale skills.** Skills encode rules; a wrong rule loses a rating fast.
  Both flagships are versions of working code, so re-derive them on release
  and ship updates (updates reach every buyer free and are a reason to post).
- **Non-exclusive.** A competitor can list a near-identical skill. The moat
  is iteration speed and depth of the quality rules, not the file.
- **Support load.** 70% of the price, but buyers will ask. Decide in advance
  whether you answer support mail and what `support_method` you declare.
