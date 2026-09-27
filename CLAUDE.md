# Job Maxing — Project Brief

Read this first. It captures every design decision made before any code was written.

## What this is

A tool that pulls analyst job ads, scores each one against the user's career goal, explains the score, and tracks the outreach process for the jobs the user chooses to pursue.

- **Version 1 (now):** built for one goal: maximising Australian PR likelihood for the owner (Ratana, Sydney-based data analyst).
- **Version 2 (later):** generalised so anyone can state their own career goal and get a rubric tuned to it. Do NOT build this yet, but keep the design ready for it (see "Architecture").

## Working agreement (important)

- **Build in stages. Stop at the end of every stage** and show the user the output. Do not start the next stage until the user approves.
- At each checkpoint, expect changes: dashboard look, fields removed, fields added. Treat these as normal, not as rework.
- The user is early in their career and learning as they build. Explain choices in plain language, define jargon briefly, keep explanations short.
- Environment: **Windows / PowerShell.** Watch for UTF-8 encoding issues when reading/writing files.
- **Keep `DECISIONS.md` up to date.** At the end of every stage, and whenever a design choice is made or changed, append a short entry: date, stage, the decision, and a one-line "Why". Include options that were rejected and why. Keep it brief, a timeline the user can skim later, not a technical changelog. Show the user the new entry at each checkpoint.

## The job-search strategy this serves

1. Automatically pull a list of jobs that match the user's needs.
2. The user picks companies they genuinely like.
3. For those, deeply research the company, find a real gap or pain point, and build one small, specific artifact that shows they can solve it (mini audit, strategy rewrite, etc.).
4. Reach out to ~3 relevant people at that company with the artifact attached.

The tool supports steps 1, 2 and 4, and gets step 3 started. **The tool informs the user's filter; it never decides for them.** The user filters and applies manually.

## Source of truth for the PR rules

The user's Notion page **"Job Search — Keywords & Filters"** (under "PR Resources"):
https://app.notion.com/p/3e403e91589b8193991ffd6894244cb4

It holds the search keywords, apply/skip rules, and ANZSCO reasoning. If this brief and that page disagree, ask the user.

## PR scoring rubric (v1)

### Step 1: Knockouts → score 0, move to "Skipped" list with the reason

- "Australian citizen" / "permanent residents only"
- Security clearance ("NV1", "baseline", "security clearance")
- Government department or agency
- Unpaid / internship / "exposure"
- Hard "3+ years experience required"

Knocked-out jobs are **never hidden**. They appear in a Skipped list with the reason, so the user can catch a rule that fires wrongly.

### Step 2: Score out of 100

| Signal | Points | Notes |
|---|---|---|
| ANZSCO fit | 45 | Based on the **team** and **language** of the ad, not the job title |
| Sponsorship signal | 25 | "482", "494", "186", "visa sponsorship", "sponsorship considered", "international applicants welcome" |
| Salary | 15 | $80k+ = 15, $70–80k = partial, below = 0 |
| Employment type | 15 | Full-time > 6–12 month contract > part-time 20+ hrs. Part-time under 20 hrs = 0 |

**Unknown rule:** if salary or employment type is not stated, give **half points** and flag it with "?".

### ANZSCO fit — how to judge it

- **Target codes (best):** 224711 Management Consultant, 224712 Organisation & Methods Analyst. Open 189 route.
- **Third choice:** 224113 Statistician. Bar is 90 points not 80. Partial credit only.
- **Dropped:** 224311 Economist (fails the duties test).
- **ICT codes:** zero places left. Treat an ICT-flavoured role as a strong negative.
- **Team decides, not title.** Finance, Strategy, Operations, Risk, People/HR, Research → target codes. IT, Technology, Engineering, Product, Digital → ICT codes.
- **Language that raises fit:** process improvement, stakeholder analysis, business efficiency, reviewing systems and procedures, organisational problems, process re-engineering, pain points, operating models.
- **Language that lowers fit:** requirements gathering, functional requirements, system specifications, user stories, acceptance criteria, software, working with developers, platform support.
- If the ad doesn't say which team, **don't guess**. Mark confidence as low/medium and suggest asking "Which team does this role sit in?" in interview.

### Deliberately NOT in the rubric

- **"Niche edge"** (payroll/tax/compliance fit): removed. It measures hireability, not PR.
- **"Can I get in?" / hireability score:** rejected by the user. They will do everything they can to get hired regardless. Do not add one.

## Output: the job card

Every scored job shows a score **and** a reason. Phrases in the reason are quoted from the ad so the user can check them.

```
ELMO Software — AI Analyst · PR score 44
- Likely code: 224712 Org & Methods Analyst · medium confidence
- Why it scores: reports to Office of the CEO; "process re-engineering", "pain points"
- Why it loses points: "functional requirements", "user stories" → ICT risk
- ❓ Unknowns: salary, employment type
- Ask in interview: "Which team does this role sit in?"
```

The full job description is always saved alongside the card.

## Calibration test (use in Stage 1)

The rubric was hand-tested on 5 real ads. Ask the user to paste them into `fixtures/`. Expected results:

| Ad | Role | Expected |
|---|---|---|
| 1 | ELMO Software — AI Analyst | ~44 (ANZSCO ~28, sponsorship 0, salary ? ~8, type ? ~8) |
| 2 | Transport for NSW — Insights Analyst | Knockout: government |
| 3 | Susquehanna — Quant Systematic Trader | ~20 (no target-code match) |
| 4 | NSW DCJ — Economic Evidence | Knockout: government (also Economist code, dropped) |
| 5 | RDA — Data Analyst/Scientist | ~42 (Statistician, no ICT language) |

User's own ranking: 5 then 1. The swap was due to the user's hireability judgement, not a rubric error. Scores within a few points of these are fine.

Known finding: sponsorship scored 0 on all 5 ads and salary was missing on every private-sector ad, so ANZSCO fit does most of the ranking work. That is acceptable.

## Architecture

**Engine separate from view.**

- **Engine** = puller + scorer + rubric. Lives in code and config files.
- **View** = where the user browses and tracks (local HTML first, Notion later).
- The rubric (knockouts, weights, phrase lists, codes) lives in a **config file** (e.g. `goals/pr_australia.yaml`), not hard-coded. In v2, a "goal → rubric" generator will produce files in this same format.
- Secrets (`APIFY_TOKEN`, `NOTION_TOKEN`, `ANTHROPIC_API_KEY`) go in `.env`, never committed. Include `.env.example`.
- Written so another person could clone it and run it with their own config.

## Build stages (stop and review after each)

1. **Scorer only, offline.** Score the 5 calibration ads from `fixtures/`. Output job cards as a simple local HTML page. *Review:* do scores match the table? Does the card show the right info?
2. **Apify puller.** Seek + Indeed first (most reliable). Small pull (~20 jobs) using keywords from the Notion page. Save raw data + full descriptions. De-duplicate. *Review:* data quality, missing fields.
3. **Score real jobs → local HTML dashboard prototype.** Cheap to iterate on the look. *Review:* layout, fields to add/remove, sorting, Skipped list.
4. **Notion sync.** Only once dashboard fields are settled. Tracker should cover: company, role, score, reason, likely code, salary, source link, full description, status, date applied, follow-up date (day 5), outreach count, research done (Y/N), artifact status, contacts. *Review:* in Notion.
5. **LinkedIn Jobs as a third source.** Best-effort only. It will get blocked sometimes; the pipeline must not break when it does.
6. **Contacts: 3 people per top company** (hiring manager etc.). Avoid fully scraping LinkedIn (ToS and ban risk). Agree the approach with the user at this stage.
7. **Deep research + artifact starter.** For companies the user stars: research the company, identify gaps/pain points, suggest artifact ideas and who to contact.
8. **(v2) Generalise.** Goal → rubric generator.

## Outreach rules to respect (from the user's Notion page)

- Never lead with sponsorship. Lead with: full work rights until February 2028.
- Follow up on day 5.
