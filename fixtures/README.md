# fixtures — real job ads, saved by hand

One `.txt` file per ad. This is where the 5 calibration ads go.

## Format

A short header, a line containing only `---`, then the ad text exactly as you
copied it from Seek / Indeed / LinkedIn.

```
company: ELMO Software
role: AI Analyst
source: https://www.seek.com.au/job/12345678
---
About the role

We are looking for an AI Analyst reporting to the Office of the CEO...
(paste the whole ad, including the "about us" blurb and the salary line if any)
```

- `company` and `role` are required. `source` and `location` are optional.
- For `python -m commands.research --ad FILE` (a job not in your list), two more optional lines help:
  `linkedin:` (the company's LinkedIn page, for contact search) and `website:`.
- Paste the **whole** ad. The scorer reads the salary line, the team name and
  the phrasing, and any of it can be in the part that feels like filler.
- Save as **UTF-8**. In Notepad: Save As → Encoding: UTF-8.
- File names don't matter; `01-elmo-ai-analyst.txt` keeps them in order.

## The 5 calibration ads

| File | Ad | Expected |
|---|---|---|
| 01 | ELMO Software — AI Analyst | ~44 |
| 02 | Transport for NSW — Insights Analyst | Knockout: government |
| 03 | Susquehanna — Quant Systematic Trader | ~20 |
| 04 | NSW DCJ — Economic Evidence | Knockout: government |
| 05 | RDA — Data Analyst/Scientist | ~42 |

Then run `python -m commands.score` and compare.
