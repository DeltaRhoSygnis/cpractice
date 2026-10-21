# Launch runbook — deterministic-autograder on Agensi.io

**Price:** $9, one-time. **One listing.** No bundle, no second listing.
**KYC is required** before a paid listing goes live. A connected payment
method is *not* the same as completed KYC — verify in the dashboard before you
assume the listing can be published.

**Scope note:** this runbook covers the minimum needed to get the listing live.
The demo video and the screenshot set are deliberately **not** required to
publish; both are conversion levers to add later, not blockers.

---

## 1. Pre-submission checklist

Mechanical checks (run these, they cover everything a reviewer would catch):

- [ ] `python3 docs/agensi/verify-package.py docs/agensi/dist/deterministic-autograder.zip` → `OK: ...`
- [ ] `head -5 docs/agensi/skills/deterministic-autograder/SKILL.md` → `name: deterministic-autograder`
- [ ] `python3 -c "from PIL import Image; print(Image.open('docs/agensi/logos/deterministic-autograder.png').size)"` → `(512, 512)`
- [ ] `python3 -c "import re;t=open('docs/agensi/listings/deterministic-autograder/listing.md').read();d=t.split('## The result',1)[1].split('## Compatibility note',1)[0];print(len(d), re.findall(r'\.\.\.|truncated', d))"` → a number above 700 and `[]`

Judgement checks:

- [ ] The description reads "Use when the user asks to..." with 3–5 trigger phrases
- [ ] `SKILL.md` is under ~1000 words; the depth is in `references/`
- [ ] Five supporting files plus a `README.md` are in the package
- [ ] Text files only; no binaries, no symlinks, no OS cruft
- [ ] No repo paths, no provider names, no internal URLs, no secrets
- [ ] Nothing in the body reads as a dangerous command or a prompt override
- [ ] Tested in two agents (Claude Code and one other)
- [ ] KYC completed

## 2. What to upload, in form order

| Step | Field | Source |
|---|---|---|
| 1 | Skill ZIP | `docs/agensi/dist/deterministic-autograder.zip` |
| 2 | Skill logo | `docs/agensi/logos/deterministic-autograder.png` |
| 2 | Skill Name | `Deterministic Autograder — Verdict Model and Test Strength` (58 chars) |
| 2 | Summary | the one-liner under `## Summary` |
| 2 | Full Description | everything under `## Full Description` |
| 3 | The request | everything under `## The request` |
| 3 | The result | everything under `## The result` — paste in full, never truncated |
| 4 | Compatibility note | the paragraph under `## Compatibility note` |
| 5 | Pricing | One-time, $9 |
| 5 | Tags / categories / use cases | the tags and use-case sentences under `## Tags / categories / use cases` |
| 5 | Permissions | the four entries under `## Permissions` |
| 6 | FAQ | every Q and A under `## FAQ` |
| 6 | Documentation link | `https://jessiejamesportfolio.vercel.app/projects/cpractice/` |

Step 6 items left blank on this launch: demo video URL, screenshots. Both are
conversion levers, not requirements.

## 3. If the review comes back

Their 8-point security scan names the check that failed. The likely failure for
this package is "dangerous commands", because the subject matter is compiling
and running student code. The fix is framing, not removal: keep every rule as
*design guidance* ("specify a sandbox this way"), never as a command, and keep
the package free of `scripts/`. Resubmitting after a named failure is free and
carries no penalty.

## 4. Distribution (after it is live)

One post per surface, showing the workflow rather than the pitch: the messy
manual task, then the agent doing it, then the link.

- [ ] Build-in-public post: "Your hidden tests pass a wrong program. Here is how
      I found out." Links the listing and the repository.
- [ ] One X/LinkedIn post with the demo clip.
- [ ] One Reddit post in the relevant teaching or C communities, following that
      community's self-promotion rules.
- [ ] Outreach list of ~30 instructors, bootcamp leads and course-tool Discord
      admins. The leave-behind is this same package (installed free in their
      agent) plus the case-study link.

## 5. Measurement

| Signal | Where | Why it matters |
|---|---|---|
| Views → installs → reviews | Agensi Creator Studio | Discovery quality |
| Case-study visits and referrers | Vercel Analytics on the portfolio | Did the listing send anyone |
| Repo clones and cloners | GitHub traffic API | Did they act on it |
| Instructor emails | Inbox | The only real conversion event |

## 6. The 90-day decision rule

| Outcome at day 90 | Action |
|---|---|
| ≥ 50 installs and ≥ 10 case-study visits, or ≥ 3 instructor emails | Channel works. Add the second listing, add the video, keep investing. |
| Installs but no instructor interest | The skill lands, the audience does not. Keep the listing as a portfolio artifact, stop investing, redirect effort to direct outreach. |
| Neither | Dead traffic channel. Leave the listing live, spend nothing more on it. |

## 7. Not doing

- The four tutor skills (`code-review`, `debugging`, `examination`,
  `retrieval`) are **not** listed. They are 47–168 word nudges on the most
  saturated keywords on the site; listing them buys noise, not installs.
- No second listing, no bundle, no free companion.
- No hosted CPractice instance.
