# Decision Log

What I decided, and why. Newest at the bottom. One or two lines per decision.

---

## 2026-09-26 · Planning session (before any code)

**What I'm building**
- A tool that pulls analyst jobs, scores them for PR likelihood, explains each score, and tracks my outreach.
- **Why:** my strategy is "artifact-first outreach": pick companies, find their pain point, build something small that solves it, then reach out. The tool handles the finding and tracking so my time goes into the research and the artifact.

**Who it's for**
- Build it so other people can use it with their own career goal, not just mine.
- **But build my PR version first, generalise later.**
- **Why:** designing a general version with zero working examples tends to produce something flexible but wrong. Get one case right, then extract the pattern.

**Engine vs. view**
- Scoring logic lives in code + a config file. Notion is only where I *look* at results.
- **Why:** keeps it reusable and lets me swap Notion for something else without rebuilding.

**How PR likelihood is measured**
- Main signal: does the role map to an ANZSCO code with an open route (224711 / 224712)? Judged by the **team and language** of the ad, not the job title.
- **Why:** ads almost never mention sponsorship. And the same "Business Analyst" title can be a target code in Finance or a dead-end ICT code in Technology.

**Rubric**
- Knockouts first (citizen/PR only, clearance, government, unpaid, hard 3+ years), then score out of 100: ANZSCO fit 45, sponsorship 25, salary 15, employment type 15.
- Missing salary or job type = half points, flagged "?".
- **Why:** so ads that just don't state salary aren't punished like low-paying ones.

**Dropped: "niche edge" (payroll/tax fit)**
- **Why:** it measures how hireable I am, not PR likelihood. My artifact outreach covers hireability.

**Rejected: a "Can I get in?" score**
- **Why:** I'll do everything I can to get hired regardless. The tool informs my filter; it doesn't decide for me. I choose what to apply for.

**Calibration test (5 real ads)**
- Rubric agreed with my gut on 4 of 5. Only swap: I ranked RDA above ELMO (rubric had them 42 vs 44).
- **Why the swap:** my own judgement on which is easier to get into, not a rubric flaw.
- Noticed: sponsorship scored 0 on every ad, so ANZSCO fit does most of the ranking. Accepted.

**Every score comes with a reason**
- Each job card shows likely code, confidence, phrases from the ad that helped/hurt, and unknowns.
- **Why:** I can check the reasoning instead of trusting a number.

**Knocked-out jobs are shown, not hidden**
- They go in a "Skipped" list with the reason.
- **Why:** so I can catch a rule that fires wrongly.

**Job sources**
- Seek + Indeed as the reliable core. LinkedIn Jobs as best-effort.
- **Why:** LinkedIn scrapers get blocked often and scraping breaks their terms. The pipeline shouldn't break when LinkedIn does.

**Build in Claude Code, not chat**
- **Why:** the chat workspace can't reach the Apify API, and "reproducible for others" needs a real code project.

**Build in stages, review each one**
- 9 stages, stop after each for me to review.
- Dashboard starts as a local web page, moves to Notion at Stage 4.
- **Why:** changing a web page is quick; changing a Notion database is slow. Experiment where it's cheap, then lock it in.

**Keep this decision log**
- **Why:** so future-me remembers what I built and why, without re-reading every chat.

---

## 2026-09-26 · Stage 1 — scorer, offline

**The rubric is a file, not code**
- `goals/pr_australia.yaml` holds every knockout phrase, weight, band and code. `jobmax/scorer.py` only applies it.
- **Why:** tuning a score becomes editing a list, not editing Python. And v2's "goal → rubric" generator just has to write this file.

**ANZSCO fit (45 pts) is built from three signals, in order**
1. **Is it an analyst occupation at all?** Off-target titles (trader, software engineer, data engineer…) → 4 pts. Checked on the job title only.
2. **Which team?** Target team 30 · statistics/research flavour 22 · IT-flavoured team 5 · no team named 18.
3. **What language?** +2 per helping phrase (max +12), −3 per ICT phrase (max −15).
- **Why the order:** a trader in a Finance team is still not 224711/224712 work, so occupation identity has to be checked before team. After that, team beats title, as the Notion page says.
- **Why 18 for "no team named":** the brief says don't guess. 18 is deliberately neutral, and confidence is marked `low` with "Which team does this role sit in?" added to the card.

**Missing salary / employment type = half points, flagged ❓**
- Salary uses the **midpoint** of a stated range. Hourly and day rates are treated as "not stated".
- **Why midpoint:** "$75–85k" is honestly an $80k job. Taking the top of the range would flatter every ad.

**Two knockout scopes, not one**
- Most knockout phrases are searched in the whole ad. A few (`internship`, `intern`, `work experience`) are searched in the **job title only**.
- **Why:** a test ad said "a strong graduate with internship experience" and got knocked out as an unpaid job. In the body those words describe the *candidate's past*; in the title they describe *the job*.
- Rejected: dropping the rule (would miss real unpaid ads) and matching only "unpaid internship" (misses ads that just say "Internship — Analyst").

**Ad files: header + `---` + pasted ad text**
- `company:`/`role:`/`source:` above the line, the whole ad below it. Read as UTF-8 with BOM tolerated.
- **Why:** it is the least work to paste into, and Stage 2's puller can build the same object from the API, so the scorer never learns where an ad came from.

**Console forced to UTF-8**
- **Why:** Windows PowerShell defaults to cp1252 and crashed printing "—". One line in `score.py` fixes it permanently.

**Checked with 31 mechanics tests on made-up ads**
- `python tests/test_scorer.py`. Covers knockouts, each team family, half-points, salary parsing, word boundaries ("api" must not match "capital").
- **Why not the 5 real ads yet:** they aren't saved in `fixtures/` — that's the next thing I need to do. The real calibration check is still outstanding.

---

## 2026-09-26 · Stage 2 — the puller

**LinkedIn is now the first source, not the third**
- Planned order was Seek + Indeed first, LinkedIn last (Stage 5). Swapped: LinkedIn first.
- **Why:** I want the company/people research component, and one LinkedIn actor returns the job, the recruiter's name, and the company's website, size, industry and about-text in the same call. Seek and Indeed return the ad only.
- **Also cheaper, which I did not expect:** $0.0015/job on LinkedIn vs $0.0025 (Seek) and $0.005 (Indeed).
- **Still true:** LinkedIn blocks more often than Seek. A failed pull now exits cleanly and leaves `data/jobs.json` untouched, so a bad day costs nothing and breaks nothing.

**Actor: `bebity/linkedin-jobs-scraper`**
- **Why:** cheapest per job, and it needs no LinkedIn cookie of mine — the scraping runs on their infrastructure, so my own LinkedIn account is not exposed to a ban. Rejected `curious_coder` ($0.002, 162k users) as it returns no recruiter.

**Apify free plan: $5/month**
- Every run prints its cost estimate first and passes a hard `maxTotalChargeUsd` cap to Apify, so a runaway actor cannot eat the month's credit even if I kill the script.
- A 20-job pull costs ~$0.03. Daily pulls are affordable.

**Structured fields are written into the ad text, not handled separately**
- LinkedIn returns `contractType: "Full-time"` as a field. The normaliser writes a short "Job facts (from the job board)" block at the top of the description.
- **Why:** the scorer reads text. This way one code path handles both pasted ads and pulled ads, and the quote on the job card is still something the board actually said.

**The company blurb is deliberately NOT scored**
- `companyDescription` is stored for Stage 7 research but kept out of the text the scorer reads.
- **Why:** a marketing line like "we serve government clients" would trip the government knockout and skip a perfectly good private-sector job.

**`--from-raw` re-reads a saved pull for free**
- **Why:** the first real pull crashed in the normaliser after the actor had already run and charged me. Re-reading the saved raw file fixed the bug without paying for the same 20 jobs twice. Raw files are the audit trail anyway.

**What the first 20 jobs revealed**
- Salary present on **1 of 20** ads. The brief expected this; it is worse than expected. ANZSCO fit and employment type do nearly all the ranking.
- Employment type present on **20 of 20** — because it is a LinkedIn field, not ad prose. Pulled jobs will almost never take the "unknown" half-point path that hand-scored ads did.
- Recruiter name present on **12 of 20**. Stage 6 starts with 60% of its contacts already collected.
- All 5 knockouts fired correctly, each quoting a real "5+ years" / "7+ years" line.
- **6 of 20 ads are recruitment agencies, including both top scorers.** Open question for Stage 3.
- **"Quality Analyst" as a search keyword pulls software-testing jobs** (QA Engineer, Manual Tester, SAP Test Analyst). Tester titles are missing from the off-target list, so a QA Engineer scored 46. Open question for Stage 3.

**Calibration, partly answered for free**
- ELMO Software — AI Analyst came through in the pull. Hand-scored 44, scorer says **56**.
- **7 points of the gap are legitimate:** LinkedIn states the employment type, so it earns 15 rather than the 8 a hand-scored unknown gets. Not a rubric error — better data.
- **5 points are the raising-language cap.** The ad hits 7 helping phrases and maxes the +12 bonus. Open question for Stage 3.

---

## 2026-09-26 · Re-scope — search and research are separate jobs

**I do the pain-point research myself. The tool stops before it.**
- Dropped from the plan: automated company research, pain-point detection, artifact suggestions (old Stage 7).
- **Why:** the research and the artifact are the part that wins the job, and they need my judgement. The tool's job is to hand me a shortlist with the people already attached, so I can start researching immediately on the jobs I actually want.

**What the tool must have ready for every job**
- Score + reason · company LinkedIn link · 3 people to contact · Seek and LinkedIn jobs in one view.
- **Why:** so that the moment I like a job, nothing stands between me and the research.

**Contacts: 2 managers + 1 analyst, per company**
- Managers = hiring power and they own the pain point. Analyst = best reply rate, and they can tell me which team the role really sits in (the question the rubric cannot answer from an ad).
- Keyed **per company, not per job** — Hays advertises four roles and that is still one set of people.
- Email addresses are worth having, but only for the shortlist (below).

**I will not build 20 artifacts for 20 jobs**
- The tracker must separate *applied* from *applied with an artifact and personalised outreach*.
- **Why:** volume applications maximise the odds; a handful of deep artifact plays are where the real chance is. Both happen at once and need tracking differently.

**Emails only for the shortlist**
- Name + LinkedIn profile costs $0.004/person; adding email search costs $0.012. Broad sweep uses the cheap mode, `--email` is run on the shortlist.
- **Why:** same logic as not building 20 artifacts — don't pay for depth on jobs I'll never pursue.

**Batching contact lookups across companies failed — reverted to one run per company**
- First design put all 15 companies in one actor run to amortise the $0.02 start fee. Asked for 60 managers; LinkedIn returned nearly all of them from the two giants (Tata ~600k staff, HCLTech ~200k) and **13 of 15 companies got nobody** — including every small company, which are the best artifact targets.
- Now one run per company per role group: ~$0.05 per company, and the 2+1 mix is guaranteed. PropertyMe went from 0 people to a CFO, a Head of Strategy & Transformation and a Business Analyst.
- **Lesson worth keeping:** cheap-per-unit was the wrong thing to optimise. Contacts are priced per company, so look up a shortlist (`--min-score`), not everything.

**Recruitment agencies are skipped by default**
- 6 of 18 companies are agencies (Hays, Reo Group, Capstone, Excolo, The Andersen Partnership). They returned nobody useful, and an agency has no pain point of its own to solve.
- **Why not delete them:** their *jobs* are still real jobs worth applying to. Only the contact lookup skips them.

**LinkedIn's job-title filter is fuzzy, so contacts are post-filtered**
- "Head of Risk" returned "Head of Information Security & Risk"; "Head of Data" returned data engineers. `contacts.exclude_titles` in the goal file drops anything security/cyber/software/test-flavoured.
- **Why:** an InfoSec manager is the ICT world this whole rubric exists to stay out of.

**Two bugs worth remembering**
- Apify rejects any run with a cost cap under **$0.05**. My analyst lookups computed $0.048 and silently failed on every company until floored.
- A run's own `usageTotalUsd` lags and often reads $0.00. Real spend comes from `/users/me/usage/monthly` — that is what the CLIs now print.

---

## 2026-09-26 · Filter fix — software testing is not analyst work

**Tester titles added to `anzsco.off_target_titles`; "Quality Analyst" dropped from search keywords**
- Added: tester, test analyst/engineer/lead/manager, QA engineer/analyst, quality assurance, quality engineer. Matched on the job title only.
- Result on the 20 pulled jobs: QA Engineer **46 → 22**, Manual Tester **15**, both now "no target-code match" instead of "224712, high confidence".
- **Why:** testing is ICT work under any team. "Quality Analyst" as a keyword only ever pulled testers, so it cost money and returned nothing useful.
- **Rejected:** adding "quality analyst" itself as an off-target title — a few real process-quality roles use it, and dropping the keyword already stops the flood.
- Note: the Notion keyword page still lists "Quality Analyst"; update it there too so the two agree.

**Search the whole of Australia, not just Sydney**
- `search.location: Australia` in the goal file. `--location` still overrides it for one run.
- **Why:** any Australian job counts toward PR, and a bigger pool gives the scorer more to rank.
- Knock-on: the government knockout named only NSW/VIC/QLD, so I added the other states and territories.

**Experience filter: Entry + Associate + Mid-Senior (LinkedIn's own levels)**
- Sent to LinkedIn as a search filter, so jobs outside these levels are never pulled or paid for.
- **Why Mid-Senior stays:** 11 of the last 20 jobs had that tag, including ELMO AI Analyst (56). LinkedIn applies it loosely, and the 3+ years knockout already catches the truly senior ones.
- **Rejected:** Entry + Associate only. Only 3 of the last 20 jobs would have passed, and 2 of those were testers.
- **Cost of this choice:** ads with no level set ("Not Applicable") drop out. Last pull that was 6 of 20, including HUB24 and PropertyMe. Worth checking after the next pull.

**Changed same day: no experience filter after all — the 3+ years knockout does it**
- `experience_levels: []`. LinkedIn is asked for every level.
- **Why:** the level filter would silently drop ads with no level set (HUB24, PropertyMe). The knockout reads the ad's own words and keeps skipped jobs visible, so a wrong call can be spotted.

---

## 2026-09-26 · Seek added, senior jobs never pulled

**Seek is the second source (`blackfalcondata/seek-scraper`)**
- `python pull.py` now pulls LinkedIn and Seek in one go; `--source seek` for one board. If one board fails, the other is still saved.
- **Why this actor:** it can drop titles by keyword on Seek's side *before* charging, and returns full description, salary and employment type. $0.01 per run + $0.002 per job.
- **Rejected:** websift (one search term per run, no exclude filter), bovi (no title exclusion at source).
- Seek gives no LinkedIn company link, so contact lookup skips Seek jobs for now.

**No senior-level jobs: titles with senior / snr / sr / lead / principal / head of / manager / director / chief are never stored**
- Lives in `search.exclude_title_words` in the goal file. Whole-word match on the title only ("Leadership Analyst" survives).
- Seek drops them free at the source. LinkedIn can't, so they are paid for, then dropped, and listed after the pull so a wrong drop is visible. Raw files keep them.
- **Why a pull filter and not a knockout:** you asked for them never to be pulled. Knockouts stay for things only the ad text reveals (3+ years, citizens only).

**Knockout fix: bare "unpaid" removed**
- It fired on "paid & unpaid parental leave". Replaced with "unpaid role / position / opportunity".

**First two-board pull: 40 jobs, 4 senior dropped, 33 new. Seek's top 3 now lead the whole list (68–70).**

**Follow-ups, same day**
- **Senior jobs from earlier pulls deleted** from `data/jobs.json` (53 → 43). Raw files still have them. The senior filter now uses the rubric's own phrase matcher, so `senior*` also catches "SeniorBusiness Analyst".
- **Seek's ICT category is a flag, not a penalty.** New `flags:` section in the goal file: a ⚠ line on the card, no points. **Why:** Seek files most Business Analyst ads under ICT whatever the team, so it's a prompt to ask, not proof.
- **Consultancies with government clients are kept.** Government knockout now has `ignore_phrases` ("working with local government", "government clients"…) that are blanked out before matching. A real government employer (City of Gold Coast, "state government team") still gets skipped.
- **New knockout: salary midpoint above $130k → "Salary suggests a senior role".** Mid-level ads cluster at $105–125k, senior-sounding ones start at $140k. A knockout, not a pull filter, because salary is a guess at seniority, so these stay visible in Skipped. Caught 6 of 43.

**Two open questions closed: no change**
- **Raising-language cap stays at +12.** ELMO scores 56 against a hand score of 44; accepted.
- **Recruitment agencies stay in the job list**, flagged, and skipped only for contact lookup. Their jobs are still real jobs.
- **Why:** both behave acceptably on real data; neither is worth a rubric change.

---

## 2026-09-26 · Job list page (first version)

**`python dashboard.py --open` → `out/dashboard.html`. Free, no network.**
- One row per job, best score first: score, role, company, city, salary, age, applicants, and tags (board · agency · ⚠ flagged · team ?).
- Click a row to open it: why it scored, the 3 contacts, links (ad · apply · company LinkedIn · website), full description.
- Filters at the top: search, board, minimum score, hide agencies. The Skipped list sits underneath with the quoted reason.
- **Why rows that expand, not full cards:** 43 jobs as full cards was a long scroll. Rows let me scan all of them, then open only the ones I like.
- **Why local HTML, not Notion yet:** layout and fields are still changing. Notion comes once they settle.
- Agency detection now also checks the company name, so Seek agencies (GWG Recruitment, Randstad) are caught too.
- **Not in it yet:** tracking status (applied, outreach sent). A static page can't remember clicks, which is why the tracker goes in Notion.

---

## 2026-09-26 · Skills fit score + salary cut-off lowered

**New: a Skills fit score (0–100) next to the PR score. It does NOT change the PR score.**
- Of the skills an ad asks for, how many I can prove. strong = 1, some = ½, none = 0, then averaged.
- My skills, levels and proof live in `profile/skills.yaml` (drafted from resume + GitHub, I edit it). Shown on each job as Have / Partly / Missing, quoted from the ad.
- Dashboard: second number on every row, "Min skills" filter, sort by PR score or Skills fit.
- **Why separate:** PR score answers "is this job good for my goal", Skills fit answers "can I do it". Mixing them would hide which one a job is strong on, and would break the calibration.
- **Changes an earlier call:** the brief said no hireability score. I asked for this one, based on proof (resume, repos), not guesswork.
- **Rejected:** merging into the PR rubric (breaks calibration) · Claude reading every ad (costs per job, scores drift between runs).
- Soft skills ("communication") left out: every ad and every resume has them.

**Salary knockout lowered: midpoint above $100k (was $130k) → "Salary suggests more experience than I have"**
- **Why:** above $100k the ads expect experience I don't have yet. Skipped jobs went 6 → 10 on salary; still visible in Skipped.

**Skills profile filled in from resume + GitHub (RatanaSovann)**
- strong = used in a job or a finished project you can link to; some = coursework or a single use; none = no proof yet. When unsure, the lower level.
- Split "Cloud data platforms" into Databricks/Snowflake/Spark (some, coursework) and Azure/AWS/GCP (none), so an Azure ad doesn't get credit for Snowflake.
- Most common gap: Requirements gathering + Agile. That same language already lowers the PR score (ICT risk), so this gap mostly shows up in jobs that are weaker for PR anyway.

---

## 2026-09-26 · Stage 4: Notion tracker

**`python sync_notion.py` sends scored jobs to the Notion tracker. `--dry-run` first shows what would change.**
- Two kinds of column. **Tool columns** (Company, PR score, Skills fit, Likely code, Why it scores, Skills have/missing, Salary, Board, Job ad) are refreshed on every sync. **Your columns** (Status, Date applied, Outreach count, Research done, Artifact status, Contacts) are filled once when a job is added, then never touched. Tested: a re-sync kept Status, Date applied and Outreach count.
- Follow-up date is a Notion formula: Date applied + 5 days. **Why:** it updates the moment you enter a date, no sync needed.
- Full ad goes in the page body. Contacts are pre-filled from contacts.json where we have them.
- Knocked-out jobs are not sent. If a rule change knocks out a job already in Notion, the sync lists it and leaves it alone. **Why:** deleting a row could delete your notes on it.
- Rows matched by the job's key, so re-running never duplicates.
- **Rejected:** Notion's built-in "Status" column type (the API can't create it; a Select does the same job) · sending skipped jobs (clutters the tracker; the dashboard already shows them).
- First sync: 26 jobs.

**Notion dashboard: views on the tracker**
- All jobs (sorted PR, then Skills) · Pipeline board by Status · Top picks (PR 40+, still To review / Researching) · Follow-ups (Applied, soonest first) · charts: Jobs by status, Artifact progress, Applied count · a Dashboard tab to pin them together.
- **Why views, not a separate page:** they update live as you change Status. No sync needed.
- Follow-ups is a list, not a calendar: Notion calendars can't use a formula date.
- The Dashboard tab was created empty; widgets have to be added by hand in Notion (the API can't place them).

---

## 2026-09-26 · Job list page, redesign

- **Summary tiles** at the top (jobs · top picks PR 40+ · strong on both, skills 60+ · skipped). Clicking one filters the list. Replaced the "min score" number boxes: presets are quicker than typing numbers.
- **One-line key** explaining PR vs Skills and the colours. Hover a score or a skill for detail.
- Rows: coloured score badges, short places ("Sydney NSW"), salary only when stated (bold), "200+ applicants". Tags only when they mean something (agency, ⚠ check, team unclear). The "linkedin" tag on every row is gone; the board is named in the grey line under the title.
- Opened row: skills as green / amber / red chips, links as buttons, a duplicate Apply link hidden when it's the same as the ad.
- Sort adds **Newest**. Skipped jobs folded into one section at the bottom.
- The "good" thresholds (PR 40, Skills 60) are defined once and shared by colours, tiles and filters.

**Dashboard links to Notion**
- "Open tracker in Notion ↗" at the top (built from NOTION_DATABASE_ID; hidden if it isn't set).
- "Track in Notion" button on each synced job, opening its own Notion page.
- Each sync saves job → Notion page links to `data/notion_pages.json`; the dashboard reads that file. **Why:** the dashboard stays free and offline, never calls Notion. Jobs not synced yet just don't get the button.

---

## 2026-09-26 · Stage 6: contacts, finished with search links

**Automatic contact lookup is blocked: the actor allows free Apify accounts only 10 runs.**
- Found while re-fetching 5 companies: every run "succeeded" with 0 people and the log said "free user run limit exceeded". It cost ~$0.17 in start fees. The empty results overwrote good contacts; restored from a backup.
- **Fixed so it can't happen again:** a run whose status message says it was refused now counts as a failure, and a company whose lookups all fail keeps its cached people.

**Instead: LinkedIn search buttons on every job ("Managers at X", "Analysts at X").**
- You open the search, pick 3 people yourself, and add them to Contacts in Notion. The search phrase lives in the goal file (`contacts.mix[].search`); the company name is tidied first ("SJ Transport Service Pty Ltd" → "SJ Transport Service").
- **Why:** free, never blocked, works for Seek jobs (no LinkedIn company link needed), and nothing is scraped, which the brief asked for. The 9 companies already found keep their people.
- **Rejected:** another scraper actor (same kind of limit likely, ban risk) · upgrading Apify (~US$29/month) · a hand-kept file of LinkedIn company links for Seek (the search buttons make it unnecessary).
- `find_contacts.py` still works if the Apify plan is ever upgraded.

**Search buttons simplified: they returned "no results"**
- **Why:** LinkedIn returns nothing for long AND / OR / NOT queries, and a quoted company name misses profiles spelled differently.
- Now one plain word per group (`search: manager`, `search: analyst`) plus an "Everyone at X" button.
- LinkedIn jobs open the company's own People tab filtered by that word (current staff only). Seek jobs, with no company page, use a plain people search: name + word.
- The IT / software / security exclusions are gone from the search; you skip those people by eye.

---

## 2026-09-26 · Stage 7: research brief + artifact ideas

**`python research.py` writes a research brief into the Notion page of each job whose Status is "Researching".** `--company X` for one company, `--dry-run` to see what it would do, `--refresh` for a new brief.
- Claude Opus 5 + web search (max 6 searches). The brief: Snapshot · Likely pain points · 3 artifact ideas (weekend-sized, from public data, using my skills) · Who to send it to (from the Contacts column) · Opening line · Sources.
- The opening line follows the outreach rules, now kept in the goal file (`outreach.rules`): never lead with sponsorship, lead with full work rights until Feb 2028, lead with the artifact.
- A "Research brief" date column marks jobs already researched, so nothing is paid for twice. Briefs are added to the page, never replace anything.
- Server-side fallback is on: if a safety check declines, the API retries on another model by itself.
- **Cost:** about $0.40–0.60 per company. Praemium: 6 searches, 56 pages found, ~$0.52.
- **Why Notion:** you asked for it to live next to the job. **Rejected:** a local file copy (for now).

**Two problems found on the first run, both fixed**
- The first Praemium brief was written from the job ad alone: the searches returned nothing, and Claude said so in its Sources. The step now counts the pages the searches actually return, and writes nothing if there are none. That brief was removed and redone.
- An old `brotli` package (1.0.9, from Anaconda) crashed the new SDK on compressed replies. Upgraded to 1.2 and pinned in requirements.txt.

**Research works on any job, not just pulled ones: `python research.py --ad my_job.txt`**
- Save the ad in the fixtures format (company / role header, `---`, the whole ad). The job is scored, added to the job list (board "manual") and to Notion with Status "Researching", then researched. Optional `linkedin:` / `website:` header lines help contacts and research.
- If the same company + role is already in the list, that job is used instead of a duplicate. If the rules would skip it, it says so and researches anyway: you asked for it.
- **Why add it to the tracker:** you chose this over a brief-only local file, so outside jobs get the same scores, status, follow-ups and contacts as pulled ones.
- **Why not a separate tool:** the research part was already its own module; only where the job came from was tied to the pulled list. One shared "create a Notion row" function now serves both the sync and this.

---

## 2026-09-26 · Stage 8: daily automatic runs

**Every day at 8:00 am, Windows Task Scheduler runs `daily.py`: pull new jobs → sync to Notion → rebuild the dashboard.**
- Set up (or changed / removed) with `schedule_daily.ps1`. Runs as you, only while logged in (no password stored). If the laptop is off at 8, it runs as soon as it's back on. Uses pythonw.exe, so no window pops up.
- Each step runs even if an earlier one fails (a blocked board never stops Notion or the dashboard). Log: `data/logs/daily-<date>.log`.
- **Budget guard:** before pulling, it checks this month's Apify spend and skips the pull if it could pass 80% of the monthly limit ($10 on this account). A daily pull costs ~$0.08, at most $0.14 → at most ~$4.20 a month.
- **Research is never automatic:** it costs money per company and needs you to choose the company.
- **Why Task Scheduler:** no cloud setup, and the API keys never leave this laptop. **Rejected:** a cloud schedule (would need the project and all three keys uploaded; runs even when the laptop is off, but you'd only look at results on the laptop anyway).

---

## 2026-09-26 · Documentation

- **`README.md`**: what the tool does, daily use, every command and its cost, setup on a new machine, configuration, dashboard, Notion, research, contacts, the daily run, what's stored where, troubleshooting.
- **`RUBRIC.md`**: how the PR score and Skills fit are calculated (with the real numbers and a worked example), and recipes for changing the rules in the YAML files without touching code.
- `.env.example` comments updated (they still mentioned Indeed, which was never used).

---

## 2026-09-27 · Pull button: real progress bar

- The bar now fills as jobs arrive: each board (LinkedIn, Seek) gets an equal slice, filled by "jobs collected so far ÷ jobs asked for", read from Apify every 5 seconds. The status line shows e.g. "Step 1 of 3: Pulling new jobs · linkedin: 12 of 20 jobs · 23% · 1:05".
- **Why:** before, the bar jumped to the middle of the pull step and sat there for 2–4 minutes, which looked frozen.
- **Rejected:** a time-based bar (would guess, and lie when a board is slow).
- Notion and dashboard steps still show "half done" while running; they're quick.
- **Bug fixed:** the page's script had a line break inside a text string, so the browser rejected the whole script and the button did nothing. Now checked with `node --check`.

---

## 2026-09-27 · Add a job by pasting its link

- **An "Add job" box on the job list page** (and `python -m commands.add LINK`). Paste a link; the ad is read, scored, added to the list, sent to Notion, and the page reloads.
- **How the ad is read (free, no Apify):** Seek — the job data Seek puts in its own page. LinkedIn — LinkedIn's public logged-out view of that one job. Any other site — the standard "JobPosting" block most careers sites (Workday, Greenhouse, Lever…) publish for Google Jobs.
- Seek and LinkedIn links get the board's own id, so a pasted job and the same job from a pull are recognised as one. Other sites show as board "manual".
- A job you paste is kept even if its title would trip the seniority filter: you chose it. The rules still score it, so a knockout still goes to Skipped.
- Salaries in other currencies keep their code (e.g. "EUR 90,000"), so they count as unknown rather than being read as dollars.
- **Why:** finding a job outside the daily pull meant copying the ad into a text file by hand.
- **Rejected:** running the Apify actors on one link (costs money, slower); asking Claude to read the page (costs money, and might reword the ad, which would break the quoted reasons on the card). If a page can't be read, the text-file route (`research --ad`) still works.
