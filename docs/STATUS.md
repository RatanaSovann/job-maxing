# Where this project is up to

Written 26 Sep 2026, before a machine restart. Read this plus `DECISIONS.md` to pick up.

## Done

**Stage 1 — scorer, offline.** ✅
Rubric lives in `goals/pr_australia.yaml`, applied by `jobmax/scorer.py`. 31 mechanics
tests pass. Job cards render to a local HTML page.

**Stage 2 — LinkedIn puller.** ✅
20 real Sydney jobs in `data/jobs.json`, raw audit copies in `data/raw/`.

**Stage 3 — contacts per company.** ◐ Working, only partly run.
9 of 18 companies looked up. The approach is now proven correct (PropertyMe returns
2 managers + 1 analyst), but 7 of those 9 were fetched with the **broken batched
method** and hold fewer people than they should.

## Commands

```powershell
python tests/test_scorer.py                     # 43 checks, no network, free
python score.py                                 # score fixtures/ -> out/jobs.html
python dashboard.py --open                      # job list page, free
python pull.py --dry-run                        # plan + cost, spends nothing
python pull.py                                  # 20 LinkedIn + 20 Seek, all Australia, no senior titles, ~$0.08
python pull.py --source seek                     # one board only
python pull.py --from-raw data/raw/<file>.json  # re-read a saved pull, free
python -m commands.refresh                      # pull + sync + dashboard (what the Pull button runs)
python -m commands.refresh --no-pull            # sync + dashboard only, free
python sync_notion.py --dry-run                 # what the Notion sync would change, free
python sync_notion.py                           # jobs -> Notion tracker; never overwrites your columns
python research.py --dry-run                    # which "Researching" jobs would get a brief
python research.py                              # brief into Notion, ~$0.40-0.60 per company (Claude)
python research.py --ad my_job.txt              # a job not in the list: adds it (board manual) + researches it
python find_contacts.py --dry-run               # what it would cost
python find_contacts.py --min-score 40          # contacts for the good jobs only
python find_contacts.py --company ELMO --email  # add email search, $0.012/person
python find_contacts.py --company X --refresh   # re-fetch one company
```

## Money

**$0.47 of $5** used this Apify cycle (26 Sep → 25 Oct). Real figure comes from
`/users/me/usage/monthly`; a single run's self-reported cost lags and reads $0.00.

| Thing | Cost |
|---|---|
| 20 LinkedIn jobs | ~$0.03 |
| Contacts, one company (2 managers + 1 analyst) | ~$0.05 |
| Same with email search | ~$0.09 |

Apify **rejects any run with a cost cap under $0.05** — `MIN_RUN_COST` in
`jobmax/contacts.py` handles it. Don't remove it.

## On disk

```
goals/pr_australia.yaml   the rubric: knockouts, weights, phrases, contact titles
profile/skills.yaml       my skills, levels, proof -> Skills fit score (separate from PR score)
jobmax/scorer.py          applies the rubric          jobmax/ads.py      reads ads
jobmax/sources.py         LinkedIn actor + normaliser jobmax/store.py    jobs.json
jobmax/contacts.py        people per company          jobmax/apify.py    API client
jobmax/render.py          HTML job cards              jobmax/config.py   reads .env
score.py  pull.py  find_contacts.py                   tests/test_scorer.py
data/jobs.json (20 jobs)  data/contacts.json (9 companies)  data/raw/ (audit)
.env  — APIFY_TOKEN and NOTION_TOKEN are set. NOT committed.
```

`.env` survives a restart. Nothing else needs re-entering.

## Update 26 Sep, later: Stage 6 finished differently

Automatic contact lookup is **blocked on the free Apify plan** (the actor allows 10 runs).
Contacts now come from **LinkedIn search buttons** on every job in the dashboard
("Managers at X", "Analysts at X"): open, pick 3 people, add them to Contacts in Notion.
Works for Seek jobs too. The two "Next" items about re-fetching and Seek contacts are closed.
Stage 7 done 26 Sep: `research.py` (brief in Notion). Stage 8 done 26 Sep: `daily.py` runs at 8:00 via Task Scheduler (`schedule_daily.ps1 -Remove` stops it). **27 Sep: scheduler removed**; pulls are now on demand with the Pull latest jobs button (`python app.py`). All v1 stages done; v2 (goal → rubric generator) not started. Tests: 57.

## Next, in order

1. **Re-fetch the 7 companies holding batch-era results.** They have fewer people than
   they should. Delete their entries from `data/contacts.json` and re-run, or use
   `--refresh`. Roughly $0.35. The 2 good ones are PropertyMe and HUB24.
2. ~~Add Seek~~ **Done 26 Sep.** Contact lookup still skips Seek jobs (no LinkedIn company
   link) — unsolved.
3. ~~Job list page~~ **First version 26 Sep** (`dashboard.py`). Awaiting your review.
4. ~~Notion tracker~~ **Done 26 Sep** (`sync_notion.py`, 26 jobs). Awaiting your review. Was: A static HTML page cannot remember what you clicked, so status
   lives in Notion: applied · personalised outreach sent · artifact built · day-5 follow-up.
   `NOTION_TOKEN` is already in `.env`; `NOTION_DATABASE_ID` is not.
5. ~~Daily scheduled pulls.~~ **Removed 27 Sep**: replaced by the Pull latest jobs button.

## Open decisions, still yours to make

- **Search filters 26 Sep:** all Australia, no experience filter (3+ years knockout decides),
  senior titles never stored (`search.exclude_title_words`).
- **Done 26 Sep:** senior jobs removed from the store · Seek ICT category shown as a ⚠ flag ·
  consultancies with government clients kept · salary above $130k knocks out as senior (lowered to $100k same day).
- **Closed 26 Sep, no change:** language cap stays +12 · agencies stay in the list (flagged).
- **Calibration** was skipped by choice. ELMO came through the pull, so ad 1 of 5 is
  checked. The other 4 never went into `fixtures/`.

## Traps already hit, don't re-hit

- Windows console is cp1252 and crashes printing `—`. Both CLIs call
  `sys.stdout.reconfigure(encoding="utf-8")`. Keep it.
- Read files with `encoding="utf-8-sig"` so a BOM from Notepad doesn't corrupt the first key.
- `companyEmployeeCount` arrives as an int, other fields as strings — `_text()` coerces.
- Python here is **3.11**, so no nested same-quotes inside f-strings (that's 3.12+).
- The company blurb is deliberately excluded from scored text: "we serve government
  clients" would otherwise trigger the government knockout.
