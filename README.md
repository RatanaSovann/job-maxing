# Job Maxing

Pulls analyst job ads every morning, scores each one against a career goal, explains
every score with quotes from the ad, and tracks the outreach for the jobs you choose
to pursue.

Version 1 is built for one goal: **the best chance of Australian permanent residency**
for a Sydney-based data analyst. The goal lives in a config file, not in the code, so
the same engine can serve other goals later (version 2).

> The tool informs your choice; it never decides for you. You pick the companies,
> you apply, you send the messages.

---

## Contents

- [How it works](#how-it-works)
- [The strategy it serves](#the-strategy-it-serves)
- [Daily use](#daily-use)
- [The two scores](#the-two-scores)
  (full guide, with how to change the rules: **[RUBRIC.md](RUBRIC.md)**)
- [Commands](#commands)
- [Setup (new machine)](#setup-new-machine)
- [Configuration](#configuration)
- [The dashboard](#the-dashboard)
- [The Notion tracker](#the-notion-tracker)
- [Research briefs](#research-briefs)
- [Finding people to contact](#finding-people-to-contact)
- [Daily automatic runs](#daily-automatic-runs)
- [Costs](#costs)
- [What's stored where](#whats-stored-where)
- [Project layout](#project-layout)
- [Tests](#tests)
- [Troubleshooting](#troubleshooting)
- [Other docs](#other-docs)

---

## How it works

```
 every day at 8:00 (Windows Task Scheduler)
        │
        ▼
 pull.py ──► Apify scrapes LinkedIn + Seek ──► data/jobs.json (de-duplicated)
        │
        ▼
 scorer: knockouts → PR score /100 + Skills fit /100, each with quoted reasons
        │
        ├──► sync_notion.py ──► Notion tracker (you track status, contacts, follow-ups)
        └──► dashboard.py   ──► out/dashboard.html (browse, filter, sort)

 on demand, for companies you pick:
 research.py ──► Claude + web search ──► research brief on the job's Notion page
```

**Engine separate from view.** The engine (puller, scorer, rubric) is code plus config
files. The views (the HTML dashboard and Notion) only display what the engine produced.

---

## The strategy it serves

1. Automatically pull jobs that match your needs. **(tool)**
2. Pick companies you genuinely like. **(you, helped by the scores)**
3. Research the company, find a real gap or pain point, build one small artifact that
   shows you can solve it (a mini audit, a dashboard mock-up, a strategy rewrite).
   **(you, started by a research brief)**
4. Reach out to about 3 people there with the artifact attached. **(you, helped by
   contact search and the tracker)**

Outreach rules: never lead with sponsorship; lead with full work rights until
February 2028; follow up on day 5.

---

## Daily use

1. **Morning:** new jobs have already been pulled, scored and sent to Notion.
   Open `out/dashboard.html` or Notion's **Top picks** tab.
2. **Pick a job you like.** In Notion set its Status to **Researching**, then run
   `python research.py`. A research brief appears on the job's Notion page.
3. **Build the artifact** from one of the brief's ideas.
4. **Find 3 people** with the dashboard's LinkedIn buttons ("Managers at X",
   "Analysts at X", "Everyone at X") and add them to the job's **Contacts** in Notion.
5. **Apply and reach out.** Set Status to **Applied** and fill in **Date applied**.
   Notion works out the **Follow-up date** (day 5) for you; the **Follow-ups** tab
   lists what's due.

Found a job somewhere else? Paste its link into the **Add job** box at the top of the
job list (open it with `python app.py`). It is read, scored, added to the list and to
Notion, free. Works with Seek, LinkedIn and most company careers pages. If a page
can't be read, save the ad as a text file and run `python research.py --ad my_job.txt`
(scored, added and researched).

---

## The two scores

> **Full explanation, worked examples and step-by-step recipes for changing the rules: [RUBRIC.md](RUBRIC.md).**

Every job gets two numbers. They are kept apart on purpose: one answers "is this job
good for my goal?", the other "can I show I do what they ask?".

### PR score (0–100)

**Step 1, knockouts.** Any of these scores 0 and moves the job to the **Skipped** list
with the reason quoted from the ad, so a rule that fires wrongly is easy to spot:

- Australian citizens / permanent residents only
- Security clearance (NV1, baseline…)
- Government department or agency (government as a *client* is fine)
- Unpaid / internship
- Hard "3+ years experience required"
- Salary midpoint above $100k (suggests more experience than you have)

**Step 2, points.**

| Signal | Points | How |
|---|---|---|
| ANZSCO fit | 45 | The **team and language** of the ad, not the job title. Finance, Strategy, Operations, Risk, People, Research → target codes 224711 / 224712. IT, Technology, Product → ICT codes (no places left, a strong negative). |
| Sponsorship signal | 25 | "482", "186", "visa sponsorship", "sponsorship considered"… |
| Salary | 15 | $80k+ = 15, $70–80k = partial, below = 0 |
| Employment type | 15 | Full-time > 6–12 month contract > part-time 20+ hrs |

If salary or employment type isn't stated: half points, flagged with **?**.
If the ad doesn't say which team, the score doesn't guess. Confidence is marked low,
and the card suggests asking "Which team does this role sit in?" in interview.

### Skills fit (0–100)

Of the skills in your profile that the ad asks for, how many you can prove:
**strong** = 1, **some** = ½, **none** = 0, averaged. Shown as green / amber / red
chips (have / partly / missing), each with what the ad says and your proof.
Soft skills everyone claims ("communication") are left out: they don't tell jobs apart.

**Colours:** green = good (PR 40+, Skills 60+), amber = okay, grey = weak.

---

## Commands

Run these from the project folder in a terminal.

| Command | What it does | Cost |
|---|---|---|
| `python daily.py` | The whole morning routine: pull → Notion → dashboard | ~$0.04–0.08 |
| `python daily.py --no-pull` | Notion sync + dashboard only | free |
| `python pull.py --dry-run` | Show what a pull would fetch and cost | free |
| `python pull.py` | Pull 20 jobs from each of LinkedIn and Seek | ~$0.04–0.08 |
| `python pull.py --source seek` | One board only | less |
| `python pull.py --from-raw data/raw/<file>.json` | Re-read a saved pull | free |
| `python -m commands.add LINK` | Add a job from its link (Seek, LinkedIn, careers pages) | free |
| `python -m commands.refresh --add LINK` | Add from a link → Notion → dashboard (what the **Add job** box does) | free |
| `python -m commands.connections` | Who you already know at the companies in your list | free |
| `python dashboard.py --open` | Rebuild and open the job list page | free |
| `python sync_notion.py --dry-run` | Show what the Notion sync would change | free |
| `python sync_notion.py` | Send scored jobs to Notion, refresh scores | free |
| `python research.py --dry-run` | Which "Researching" jobs would get a brief | free |
| `python research.py` | Brief for every job with Status "Researching" | ~$0.40–0.60 each |
| `python research.py --company Praemium` | Brief for one company, any status | ~$0.40–0.60 |
| `python research.py --company X --refresh` | A new brief even if one exists | ~$0.40–0.60 |
| `python research.py --ad my_job.txt` | Add + score + research a job not in the list | ~$0.40–0.60 |
| `python score.py` | Score the hand-saved ads in `fixtures/` (calibration) | free |
| `python tests/test_scorer.py` | Run the tests | free |
| `python find_contacts.py` | Automatic contact lookup. **Blocked on Apify's free plan**, see below | — |

Every paid command has a `--dry-run` that spends nothing.

---

## Setup (new machine)

Needs **Windows**, **Python 3.11+** (Anaconda is fine) and accounts on
[Apify](https://apify.com) (free plan), [Notion](https://notion.so) and
[Anthropic](https://console.anthropic.com).

1. **Install the packages**
   ```
   pip install -r requirements.txt
   ```
2. **Add your keys.** Copy `.env.example` to `.env` and fill it in: no quotes, no
   spaces around `=`. `.env` is never committed.
3. **Set up Notion.**
   - Create an integration at notion.so/my-integrations; its secret is `NOTION_TOKEN`.
   - Create an empty full-page database. Its ID is the 32-character code in its link;
     put it in `NOTION_DATABASE_ID`.
   - On the database: **•••** → **Connections** → add your integration. (Without
     this, Notion answers "Could not find database".)
   - Run `python sync_notion.py`. It creates all the columns itself.
4. **Add your skills.** Edit `profile/skills.yaml`: a level and proof for each skill.
5. **Check it works**
   ```
   python tests/test_scorer.py
   python pull.py --dry-run
   python daily.py
   python dashboard.py --open
   ```
6. **Turn on the daily run**
   ```
   powershell -ExecutionPolicy Bypass -File schedule_daily.ps1
   ```

To use it for **someone else**, give them their own `.env`, `profile/skills.yaml` and,
if their goal differs, their own goal file (see below).

---

## Configuration

Nothing about the goal is hard-coded. Change behaviour in these files, not the code.

### `goals/pr_australia.yaml` — the rubric

| Section | Controls |
|---|---|
| `knockouts` | Rules that score a job 0, the phrases that trigger them, and `ignore_phrases` for false alarms (e.g. "government clients") |
| `anzsco` | Codes, which teams map to which code, and language that raises or lowers fit |
| `sponsorship`, `salary`, `employment_type` | Points and phrases for each signal |
| `flags` | Warnings shown on a job with no effect on points (e.g. Seek files it under ICT) |
| `questions` | What to ask in interview when something is unknown |
| `search` | Where to pull from, and title words never to store (senior, lead, manager…) |
| `search_keywords` | The job titles each pull searches for |
| `contacts` | Who to look for at a company, and the one-word LinkedIn searches (`search: manager`) |
| `outreach` | Rules the research brief follows when drafting an opening line |

Phrase matching: whole words, case doesn't matter, a trailing "s" is allowed,
and a trailing `*` matches the start of a word (`epidemiolog*`).

Source of truth for the PR rules: the Notion page **"Job Search — Keywords & Filters"**
(under "PR Resources").

### `profile/skills.yaml` — your skills

Each skill has a `level` (strong / some / none), `evidence` (a resume line or repo,
shown on the card) and `phrases` (how ads word it). Update it when you finish a
project or learn a tool, then run `python dashboard.py --open`.

### `.env` — keys

`APIFY_TOKEN`, `NOTION_TOKEN`, `NOTION_DATABASE_ID`, `ANTHROPIC_API_KEY`.

---

## The dashboard

`out/dashboard.html`, rebuilt every morning, or on demand with `python dashboard.py --open`.
It works offline and costs nothing to rebuild.

- **Tiles:** jobs to look at · top picks (PR 40+) · strong on both (PR 40+ and
  Skills 60+) · skipped. Click one to filter.
- **Search, sort** (PR score, Skills fit, Newest), board filter, hide agencies.
- **Click a job** to see why it scored, its skills chips, links (the ad,
  **Track in Notion**, company LinkedIn), people to contact, and the full ad.
- Jobs **posted over 30 days ago** drop off the page (they stay in `data/jobs.json`,
  and in Notion if they were sent while fresh). Pulls don't keep them in the first place.
  Jobs you added from a link stay whatever their age.
- **Skipped** jobs are folded at the bottom with the rule that fired, so you can
  check the rules.
- **Open tracker in Notion ↗** at the top right.
- **Add job** (needs `python app.py`): paste a job link, and the job is added, sent to
  Notion and the page reloads with it. Jobs you add are kept even if the seniority
  filter would have dropped them; the rules still score them (a knockout lands in Skipped).

---

## The Notion tracker

One row per scored job. Knocked-out jobs are not sent; they stay on the dashboard's
Skipped list.

| Filled by the tool (refreshed every sync) | Yours (set once when added, never overwritten) |
|---|---|
| Role, Company, PR score, Skills fit, Likely code, Why it scores, Skills have / missing, Salary, Board, Job ad, Research brief (date) | Status, Date applied, Outreach count, Research done, Artifact status, Contacts |

- **Follow-up date** = Date applied + 5 days (a Notion formula, updates instantly).
- **Status:** To review → Researching → Applied → Followed up → Interview / Rejected /
  Not pursuing.
- The full ad is on each job's page, and so is any research brief.
- If a rule change later knocks out a job that's already in Notion, the sync lists it
  and leaves it alone: deleting a row could delete your notes.

**Views (tabs):** All jobs · Pipeline (board by Status) · Top picks (PR 40+, not yet
acted on) · Follow-ups · Jobs by status (chart) · Artifacts (chart) · Applied (count) ·
Dashboard (empty; add the views above as widgets by hand if you want one screen).

---

## Research briefs

`python research.py` researches every job whose Status is **Researching** and adds a
brief to the bottom of its Notion page:

- **Snapshot:** what the company does, its size, what's changing now
- **Likely pain points:** 2–3, each with evidence from the ad or a linked source
- **Artifact ideas:** 3, weekend-sized, built from public data, using your skills
- **Who to send it to:** from the job's Contacts, or which titles to look for
- **Opening line:** follows the outreach rules
- **Sources:** clickable links

Claude Opus 5 with web search (up to 6 searches). The **Research brief** column gets
the date, so a job isn't researched twice (use `--refresh` for a new brief). If the
searches return nothing, **nothing is written**: a brief from the job ad alone would
look like research without being research. Check the links before relying on the
brief.

**Jobs not in your list:** save the ad as a text file in this format (see
`fixtures/README.md`):

```
company: Example Co
role: Operations Analyst
location: Sydney NSW
linkedin: https://www.linkedin.com/company/example-co
---
(paste the whole ad here)
```

then run `python research.py --ad that_file.txt`. Only `company` and `role` are required.

---

## Finding people to contact

**Start with people you already know.** Download your LinkedIn connections:
LinkedIn → Settings → Data privacy → Get a copy of your data → pick **Connections**.
LinkedIn emails a link, usually within minutes. Unzip it and save `Connections.csv` in
`data/`. Then:

- `python -m commands.connections` lists every company in your job list where you
  know someone, with their position and profile link.
- The dashboard tags those jobs **you know N** and lists the people first under
  *People to contact*.
- Research briefs are told about them, and put them first in "Who to send it to".

Matching is by company name, ignoring words like "Australia", "Group" and "Pty Ltd".
Each person shows the employer *they* typed, so you can spot a wrong match. The file
is never committed (it holds other people's details). Download a fresh copy now and then.

Every job on the dashboard also has LinkedIn search buttons:

- **Managers at X** and **Analysts at X.** For LinkedIn jobs these open the company's
  **People** tab filtered by one word (current staff only). For Seek jobs they run a
  people search on the company name plus that word.
- **Everyone at X,** for when a keyword misses someone (a "Head of Finance" isn't
  tagged "manager").

Pick 3 people yourself and add them to **Contacts** in Notion. Nothing is scraped,
and it works for every board.

Automatic lookup (`find_contacts.py`) worked for 9 companies, but the Apify actor
allows free accounts only 10 runs, so it is now blocked. Those contacts are kept and
shown. It works again if the Apify plan is upgraded.

---

## Daily automatic runs

**Windows Task Scheduler** (built into Windows, not Apify) starts `daily.py` at 8:00
every day. It runs pull → Notion sync → dashboard.

- Runs on **your laptop**, only while you're logged in (no password stored). If the
  laptop is off at 8:00, it runs as soon as it's back on. No window pops up.
- Only the scraping happens on Apify's servers; everything else runs locally.
- If one step fails, the others still run.
- **Budget guard:** skips the pull if it could take this month's Apify spend past 80%
  of the limit.
- **Research is never automatic:** it costs money and needs your choice.
- Log of each run: `data/logs/daily-<date>.log`.

```
powershell -ExecutionPolicy Bypass -File schedule_daily.ps1               # set up (8:00)
powershell -ExecutionPolicy Bypass -File schedule_daily.ps1 -Time 07:30   # change time
powershell -ExecutionPolicy Bypass -File schedule_daily.ps1 -Remove       # stop
```

To see it: Start menu → **Task Scheduler** → Task Scheduler Library → **JobMaxing Daily**.

---

## Costs

| What | Service | Cost |
|---|---|---|
| Daily pull (20 LinkedIn + 20 Seek) | Apify | ~$0.04–0.08, capped at $0.14 |
| A month of daily pulls | Apify | ~$1–2.50 (free plan limit: $10/month) |
| One research brief | Anthropic | ~$0.40–0.60 |
| Dashboard, Notion sync, scoring, tests | — | free |

---

## What's stored where

Everything is in the project folder (about 2 MB). Notion holds a copy of what you track.

| Path | Contents |
|---|---|
| `data/jobs.json` | Every job pulled, with the full ad. The main list everything reads from. |
| `data/raw/` | The untouched scraper output of each pull (audit trail). Grows ~2–3 MB a month. |
| `data/contacts.json` | People found by the old automatic lookup (9 companies) |
| `data/notion_pages.json` | Which Notion page belongs to which job (for dashboard links) |
| `data/logs/` | One log per daily run |
| `out/dashboard.html` | The job list page |
| `profile/` | Your resume and `skills.yaml` |
| `goals/` | The rubric |
| `.env` | Your keys |

**Only in Notion:** research briefs and your tracking (status, dates, contacts, notes).

**Not in git:** `.env`, `data/`, `out/`, and the resume files in `profile/`
(see `.gitignore`). `profile/skills.yaml` *is* included.

**No backup:** if the laptop is lost, everything except Notion goes with it. Putting
the project folder in OneDrive is the simplest fix.

---

## Project layout

```
daily.py            the morning routine (what Task Scheduler runs)
pull.py             pull jobs from LinkedIn + Seek via Apify
dashboard.py        build out/dashboard.html
sync_notion.py      send scored jobs to Notion
research.py         research briefs into Notion (Claude + web search)
find_contacts.py    automatic contact lookup (blocked on the free Apify plan)
score.py            score hand-saved ads in fixtures/ (calibration)
schedule_daily.ps1  set up / change / remove the daily run

jobmax/
  scorer.py         applies the rubric: knockouts, points, quoted reasons
  skills.py         Skills fit against profile/skills.yaml
  ads.py            reads ad files and job records
  sources.py        LinkedIn / Seek / manual job records
  links.py          reads a job ad from a pasted link
  apify.py          Apify client (runs, costs, refused runs)
  store.py          data/jobs.json, de-duplication
  contacts.py       contact lookup + LinkedIn search links
  notion.py         Notion client, tracker columns, page content
  research.py       the research prompt and Claude call
  render.py         the HTML pages
  config.py         reads .env

goals/pr_australia.yaml   the rubric
profile/skills.yaml       your skills
fixtures/                 hand-saved ads (format in fixtures/README.md)
tests/test_scorer.py      tests
```

---

## Tests

```
python tests/test_scorer.py
```

57 checks, no network, free. They cover knockouts (and false alarms like "unpaid
parental leave"), points, salary parsing, phrase matching, skills fit, contact search
links, the research brief → Notion conversion, and hand-saved jobs.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `... is empty or missing in .env` | Fill that key in `.env`: no quotes, no spaces around `=`. |
| Notion: "Could not find database" | Share the database with your integration: **•••** → **Connections**. |
| Apify: "free user run limit exceeded" | That actor's free runs are used up. Pulls are unaffected; contact lookup is (use the LinkedIn buttons). |
| `anthropic.APIConnectionError` right away | An old `brotli` package: `pip install -U "brotli>=1.2"`. |
| Garbled "—" or "→" in the console | Windows console encoding; the scripts handle it. If a new script shows it, add `sys.stdout.reconfigure(encoding="utf-8")`. |
| The 8:00 run didn't happen | Laptop off or logged out; it runs at next login. Check Task Scheduler → JobMaxing Daily → Last Run Result, and `data/logs/`. |
| A job was skipped wrongly | Read the quoted reason on the dashboard's Skipped list; fix the phrase in the goal file's `knockouts`, or add an `ignore_phrases` entry. |
| A research brief failed | Nothing was written, and it says why. Try again later, or `--refresh` next time. |

---

## Other docs

- `CLAUDE.md`: the original project brief and design decisions made before any code.
- `RUBRIC.md`: how the scores are calculated, and how to change the rules.
- `DECISIONS.md`: a dated timeline of every design choice, including the rejected options.
- `STATUS.md`: where the build is up to.
- `fixtures/README.md`: the format for hand-saved job ads.
