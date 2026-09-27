# How the ranking works, and how to change it

Every job gets two separate numbers:

- **PR score (0–100):** how much this job helps your goal (Australian PR).
  Rules: `goals/pr_australia.yaml`.
- **Skills fit (0–100):** how much of what the ad asks for you can prove.
  Your skills: `profile/skills.yaml`.

Neither number affects the other. All the rules, points and phrases live in those two
files; the code only applies them. **To change how jobs are ranked, edit the YAML
files. You never need to touch the Python.**

---

## Part 1: How the PR score works

```
job ad
  │
  ├─ Step 1: knockouts ── any rule fires? ──► score 0, "Skipped" list, reason quoted
  │
  └─ Step 2: four signals, added up
        ANZSCO fit          up to 45
        Sponsorship signal  up to 25
        Salary              up to 15
        Employment type     up to 15
                            ───────
                            up to 100
```

The scorer reads the **job title, the company name and the full ad text**. It does
*not* read the company's "About us" blurb from the job board: "we serve government
clients" in a blurb would otherwise knock out the job.

### Step 1: Knockouts

Each rule is a list of phrases. If the ad contains any of them, the job scores **0**
and moves to the **Skipped** list, with the matching sentence quoted so you can check
the rule fired correctly. Every rule is checked, so a job can show several reasons.

| Rule | Fires on (examples) | Special behaviour |
|---|---|---|
| Citizens / permanent residents only | "australian citizen", "permanent residents only", "no visa sponsorship", "unable to sponsor" | — |
| Security clearance required | "security clearance", "nv1", "baseline clearance", "agsva" | — |
| Government department or agency | "nsw government", "department of", "city council", "public service" | `ignore_phrases` ("government clients", "working with local government"…) are blanked out first, so consultancies that serve government are kept |
| Unpaid / internship | "unpaid role", "this role is unpaid" | `role_phrases` ("internship", "intern") are checked in the **job title only**: in the body, "internship" is usually the candidate's own past |
| Hard experience requirement (3+ years) | "3+ years", "minimum 3 years" | — |
| Salary suggests more experience than you have | no phrases | `salary_above: 100000`: fires if the stated salary's midpoint is above $100k |

Knocked-out jobs are **never hidden**. They're on the dashboard's Skipped list, so a
rule that fires wrongly is easy to spot.

### Step 2a: ANZSCO fit (up to 45 points)

This decides which occupation code the job would count toward. The **team** decides,
not the job title. It's worked out in this order:

**1. Off-target title?** If the *title* contains words like "trader", "portfolio
manager" or "software engineer", the job gets **4 points** ("no target-code match")
and the team check is skipped.

**2. Which team?** The ad is searched for team phrases. The **first team in the file
that matches wins**, in this order:

| Team | Example phrases | Base points | Code | Confidence |
|---|---|---|---|---|
| Target team (Finance / Strategy / Ops / Risk / People / Research) | "finance team", "strategy team", "commercial team" | **30** | 224712 Org & Methods Analyst | high |
| IT-flavoured team | "technology team", "it department", "engineering team" | **5** | ICT code: no places left | high |
| Research / statistics flavour | "statistical analysis", "statistical modelling", "survey design" | **22** | 224113 Statistician (bar is 90 points, not 80) | medium |
| **No team found** | — | **18** | 224711 / 224712 (team not stated) | **low** |

When no team is found, the scorer doesn't guess. It marks confidence **low**, tags the
job "team unclear", and suggests asking "Which team does this role sit in?" in interview.

Because the first match wins, the order in the file matters: an ad that mentions both
"finance team" and "technology team" counts as a target team.

**3. Language adjustment.** On top of the base points:

| | Example phrases | Per phrase | Cap |
|---|---|---|---|
| **Raises** fit (consulting / org-and-methods work) | "process improvement", "process re-engineering", "stakeholder analysis", "pain points", "operating model" | **+2** | **+12** |
| **Lowers** fit (sounds like ICT work) | "requirements gathering", "functional requirements", "user stories", "acceptance criteria", "working with developers" | **−3** | **−15** |

Each phrase counts once, however often it appears. The final ANZSCO fit is kept
between 0 and 45.

### Step 2b: Sponsorship signal (0 or 25)

**25** if the ad mentions any of: "visa sponsorship", "sponsorship available",
"sponsorship considered", "482", "494", "186", "international applicants welcome"…
Otherwise **0**. That's normal, since most ads don't mention it.

### Step 2c: Salary (up to 15)

The scorer finds every dollar figure in the ad and takes the **midpoint of the range**
("$80,000 – $90,000" → $85,000). Figures outside $30k–$500k are ignored: those are
hourly or daily rates, or numbers from the company blurb.

| Midpoint | Points |
|---|---|
| $80k or more | **15** |
| $70k – $80k | **8** |
| under $70k | **0** |
| not stated | **7.5** (half), flagged **❓**, suggests asking "What's the salary range?" |

(Above $100k the job never reaches this step: the salary knockout skips it.)

### Step 2d: Employment type (up to 15)

The first type that matches:

| Type | Example phrases | Points |
|---|---|---|
| Full-time | "full-time", "permanent role", "38 hours" | **15** |
| Contract | "fixed term", "12 month contract" | **11** |
| Part-time | "part-time" | **7**, plus "check it's 20+ hours a week" |
| Casual | "casual role" | **0** |
| not stated | — | **7.5** (half), flagged **❓** |

### Flags (warnings, no points)

A flag adds a ⚠ line to the job without changing the score. There's one now: **"Seek
lists this under ICT, ask which team it sits in."** Seek files most Business Analyst
ads under ICT whatever the team, so it's a prompt to check, not proof.

### Worked example: Praemium, Junior Strategy Analyst → 54

| Signal | Why | Points |
|---|---|---|
| ANZSCO fit | Target team ("Strategy team") = 30, plus "stakeholder engagement" +2 | 32 / 45 |
| Sponsorship | Not mentioned | 0 / 25 |
| Salary | Not stated → half | 7.5 / 15 |
| Employment type | "Full-time" | 15 / 15 |
| **Total** | 54.5, rounded | **54** |

Likely code: 224712 Org & Methods Analyst, high confidence.

---

## Part 2: How Skills fit works

`profile/skills.yaml` lists your skills. For each job:

1. Find which of your skills the ad asks for (using each skill's `phrases`).
2. Score each one by your level: **strong = 1**, **some = ½**, **none = 0**.
3. Average them, then × 100.

Skills the ad doesn't mention are ignored: they neither help nor hurt. If the ad
names none of your skills, Skills fit shows "–".

**Praemium example:** the ad asks for Excel (strong = 1), Dashboards & reporting
(strong = 1) and Stakeholder engagement (some = ½). (1 + 1 + ½) ÷ 3 = **83**.

---

## Part 3: How to change things

### The workflow for any change

1. **Edit** the YAML file in any text editor (VS Code, Notepad). Save as **UTF-8**.
2. **Look at the effect:** `python dashboard.py --open`. It's free and rescores everything.
3. **Run the tests:** `python tests/test_scorer.py`. A test that fails after a
   *deliberate* change just means the test still describes the old rule; update its
   expected value (as was done when the salary cut-off moved from $130k to $100k).
4. **Update Notion:** `python sync_notion.py`. It refreshes the scores and reasons on
   every row. Your own columns (Status, dates, contacts) are never touched.
5. **Log it:** add a line to `DECISIONS.md` saying what you changed and why.

Nothing is lost by experimenting: scores are recalculated from the saved ads every
time, so you can change a rule, look, and change it back.

### YAML in 30 seconds

- **Indentation is spaces, never tabs,** and it matters: it shows what belongs to what.
- A list item starts with `- `.
- Put a phrase in quotes if it contains `:` or `#`, or starts with a symbol:
  `- "3+ years"`, `- "salary: negotiable"`.
- A line starting with `#` is a comment and is ignored.

If you break the format, the scripts stop with an error naming the line. Undo your
last edit and try again.

### Phrase matching rules

- Case doesn't matter: "Finance Team" matches `finance team`.
- Whole words only: `api` doesn't match "capital".
- A trailing "s" is allowed: `sprint` also matches "sprints".
- A trailing `*` matches the start of a word: `epidemiolog*` matches "epidemiology"
  and "epidemiologist".
- Spaces match line breaks too, so a phrase split across two lines still matches.
- If two phrases overlap, only the longer one counts: "non-functional requirements"
  isn't also counted as "functional requirements".

---

### Recipes

#### A rule fired wrongly: ignore a harmless phrase

Say "our government-owned shareholder" keeps knocking out good jobs. Add it to that
rule's `ignore_phrases` (create the list if the rule doesn't have one):

```yaml
  - id: government
    reason: Government department or agency
    phrases:
      - nsw government
      ...
    ignore_phrases:
      - government clients
      - government-owned shareholder     # ← new
```

#### A rule should catch something it misses: add a phrase

```yaml
  - id: citizens_only
    phrases:
      - australian citizen
      - must hold australian citizenship   # ← new
```

#### Add a new knockout rule

```yaml
knockouts:
  ...
  - id: relocation
    reason: Requires relocating overseas
    phrases:
      - based in singapore
      - relocation to london
```

`reason` is what you'll see on the Skipped list. `role_phrases:` (title only) and
`ignore_phrases:` work here too.

#### Change the salary cut-off

```yaml
  - id: senior_salary
    reason: Salary suggests more experience than I have
    salary_above: 110000     # was 100000
```

To turn the rule off completely, delete the whole `- id: senior_salary` block.

#### Change how much a signal is worth

Each signal has a `max_points`. **Keep the four adding up to 100**, or scores stop
being "out of 100". For example, to weight salary more and sponsorship less:

```yaml
sponsorship:
  max_points: 20        # was 25
salary:
  max_points: 20        # was 15
  bands:
    - {min: 80000, points: 20, label: "$80k+"}      # top band = the new max
    - {min: 70000, points: 11, label: "$70-80k"}
    - {min: 0,     points: 0,  label: "under $70k"}
```

When you change a `max_points`, also update the points inside that section (salary
`bands`, employment `types`, ANZSCO team `points`) so the best case still equals the max.

#### Change salary bands

```yaml
salary:
  bands:                # checked top to bottom; the first band the salary reaches wins
    - {min: 90000, points: 15, label: "$90k+"}
    - {min: 80000, points: 11, label: "$80-90k"}
    - {min: 70000, points: 6,  label: "$70-80k"}
    - {min: 0,     points: 0,  label: "under $70k"}
```

#### Make a team count more or less

```yaml
  teams:
    - id: target
      points: 30          # base points when this team is found
      phrases:
        - finance team
        - pricing team    # ← teach it a new team name
```

To add a whole new team, copy an existing team block, give it a new `id`, `label`,
`points`, `code_ref` (one of the names under `codes:`) and `confidence`. Remember the
**first matching team wins**, so put more specific teams higher in the list.

#### Tune the language adjustment

```yaml
  language:
    raise:
      points_each: 2
      cap: 12           # most it can add
      phrases:
        - process improvement
        - root cause analysis     # ← new
    lower:
      points_each: 3
      cap: 15           # most it can take away
      phrases:
        - user stories
```

#### Add a warning without changing the score

```yaml
flags:
  - note: Mentions on-call work, ask about hours
    phrases:
      - on-call
      - after-hours support
```

#### Change what gets pulled at all

These don't change scores; they change which jobs come in:

```yaml
search:
  exclude_title_words:     # titles with these words are never stored
    - senior*
    - lead
    - manager
search_keywords:
  primary:                 # what the daily pull searches for
    - Business Analyst
    - Operations Analyst
```

`pull.py` uses the `primary` group. Try another with `python pull.py --group core`.

#### Update your skills

In `profile/skills.yaml`:

```yaml
  - name: Tableau
    level: some                                  # was none
    evidence: "repo sales-dashboard: Tableau"    # shown on the job card
    phrases: [tableau]
```

Add a new skill by copying a block. Choose `phrases` the way ads word it, and check a
few ads to make sure the phrase doesn't match something unrelated. For example, `excel`
alone would match "excel in your role", which is why the Excel skill uses
"advanced excel", "in excel", "excel skill" and so on.

#### Change what counts as "good" (the colours and tiles)

This is the only setting in code, because it's about display, not scoring. In
`jobmax/render.py`:

```python
PR_GOOD, PR_OK = 40, 25      # green from 40, amber from 25
FIT_GOOD, FIT_OK = 60, 30
```

The Notion **Top picks** view has its own filter (PR score ≥ 40); change it in Notion.

---

## Part 4: A second goal (later)

The rubric file is the whole goal. To score jobs for a different goal, copy
`goals/pr_australia.yaml` to e.g. `goals/pay_growth.yaml`, change its rules, and pass it:

```
python dashboard.py --goal goals/pay_growth.yaml --out out/pay_growth.html
```

`pull.py`, `dashboard.py`, `sync_notion.py`, `research.py`, `score.py` and `find_contacts.py` all take `--goal`
(the 8:00 daily run uses the default file). Version 2 will generate these files from a plain-English
goal. The format above is what it will produce.
