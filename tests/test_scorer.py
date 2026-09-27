"""Smoke tests for the engine, on short made-up ads.

These prove the mechanics work. The real calibration is the 5 hand-scored ads
in fixtures/ — run `python -m commands.score` for that.

    python tests/test_scorer.py
"""

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jobmax.ads import parse_ad  # noqa: E402
from jobmax.scorer import Rubric, find, parse_salary  # noqa: E402
from jobmax.contacts import search_links, search_name  # noqa: E402
from jobmax.skills import SkillProfile  # noqa: E402
from jobmax.sources import from_ad, too_old  # noqa: E402
from jobmax import connections  # noqa: E402
from jobmax.notion import markdown_blocks  # noqa: E402
from jobmax.research import _search_outcomes, people_from  # noqa: E402
from jobmax.links import _CLOSED_WORDS, _job_id, _job_postings, _salary, html_text  # noqa: E402
from jobmax.sources import closed  # noqa: E402
from commands.check_open import due  # noqa: E402

RUBRIC = Rubric.load(ROOT / "goals" / "pr_australia.yaml")


def ad(role: str, body: str, company: str = "Test Co"):
    return parse_ad(f"company: {company}\nrole: {role}\n---\n{body}")


def check(label: str, got, want):
    status = "ok  " if got == want else "FAIL"
    print(f"{status} {label}: got {got!r}, want {want!r}")
    return got == want


results = []

# --- knockouts ------------------------------------------------------------
r = RUBRIC.score(ad("Insights Analyst", "The NSW Government is hiring. Great team."))
results.append(check("government knockout", r.knockouts[0][0], "Government department or agency"))
results.append(check("knockout scores 0", r.total, 0))
results.append(check("knockout quotes context", "NSW Government" in r.knockouts[0][1], True))

r = RUBRIC.score(ad("Data Analyst", "You must be an Australian citizen."))
results.append(check("citizen knockout", r.knockouts[0][0], "Citizens / permanent residents only"))

r = RUBRIC.score(ad("Data Analyst", "We need at least 3 years of experience."))
results.append(check("experience knockout", r.knockouts[0][0], "Hard experience requirement (3+ years)"))

r = RUBRIC.score(ad("Business Analyst", "A consultancy working with local government and SMEs."))
results.append(check("government as client is not a knockout", r.skipped, False))

r = RUBRIC.score(ad("Business Analyst", "Paid & unpaid parental leave for all staff."))
results.append(check("unpaid parental leave is not a knockout", r.skipped, False))

r = RUBRIC.score(ad("Business Analyst", "Salary: $150,000 - $160,000 plus super."))
results.append(check("senior salary knockout", r.knockouts[0][0] if r.skipped else None,
                     "Salary suggests more experience than I have"))

r = RUBRIC.score(ad("Business Analyst", "Salary: $110,000 - $125,000 plus super."))
results.append(check("salary above $100k knocked out", r.skipped, True))

r = RUBRIC.score(ad("Business Analyst", "Salary: $90,000 - $100,000 plus super."))
results.append(check("salary up to $100k kept", r.skipped, False))

r = RUBRIC.score(ad("Business Analyst",
                    "Seek category: Information & Communication Technology › Business/Systems Analysts"))
results.append(check("Seek ICT category flagged, not scored down",
                     (len(r.flags), r.skipped), (1, False)))

# --- target team + raising language, salary and type unknown --------------
r = RUBRIC.score(ad(
    "Business Analyst",
    "Join the finance team. You will drive process improvement and map pain points.",
))
# 30 base + 2 raising phrases (+4) = 34, sponsorship 0, salary 7.5?, type 7.5?
results.append(check("target team score", r.total, 49))
results.append(check("target code", r.likely_code, "224712 Org & Methods Analyst"))
results.append(check("confidence high", r.confidence, "high"))
results.append(check("unknowns flagged", sorted(r.unknowns), ["employment type", "salary"]))
results.append(check("half points flagged",
                     [c.unknown for c in r.components], [False, False, True, True]))

# --- ICT team + lowering language ----------------------------------------
r = RUBRIC.score(ad(
    "Business Analyst",
    "Sits in the technology team. Requirements gathering, user stories, "
    "acceptance criteria, working with developers. Full-time. $95,000 package.",
))
# 5 base - 12 (4 lowering phrases) -> 0, salary 15, type 15
results.append(check("ICT team sinks the score", r.total, 30))
results.append(check("ICT code named", r.likely_code, "ICT code (2611xx / 2613xx)"))

# --- no team named -------------------------------------------------------
r = RUBRIC.score(ad("Reporting Analyst", "Build dashboards for a growing business."))
results.append(check("no team = low confidence", r.confidence, "low"))
results.append(check("no team asks the question",
                     r.questions[0], "Which team does this role sit in?"))

# --- off-target title beats everything -----------------------------------
r = RUBRIC.score(ad(
    "Quantitative Systematic Trader",
    "Join our trading desk. Work with developers on software development in C++.",
))
results.append(check("off-target title", r.likely_code, "no target-code match"))
results.append(check("off-target fit points", r.components[0].points, 0))

# --- sponsorship ---------------------------------------------------------
r = RUBRIC.score(ad("Process Analyst", "Visa sponsorship available for the right person."))
results.append(check("sponsorship full points", r.components[1].points, 25))

# --- salary parsing ------------------------------------------------------
results.append(check("range midpoint", parse_salary("$80,000 - $90,000 + super"), 85000))
results.append(check("k notation", parse_salary("$85k plus super"), 85000))
results.append(check("plain digits", parse_salary("Salary: $78000"), 78000))
results.append(check("hourly rate ignored", parse_salary("$45 per hour"), None))
results.append(check("no salary stated", parse_salary("Competitive salary on offer"), None))
results.append(check("company blurb number ignored", parse_salary("We serve 20,000 customers"), None))

r = RUBRIC.score(ad("Process Analyst", "Finance team role paying $75,000. Full-time."))
results.append(check("mid salary band partial", r.components[2].points, 8))

# --- phrase matching ------------------------------------------------------
results.append(check("word boundary", find("Our capital city", ["api"]), []))
results.append(check("plural tolerated", len(find("We run sprints", ["sprint"])), 1))
results.append(check("stem match", len(find("epidemiology work", ["epidemiolog*"])), 1))
results.append(check("line break inside phrase",
                     len(find("process\n  improvement", ["process improvement"])), 1))
results.append(check("overlap counted once",
                     len(find("non-functional requirements",
                              ["functional requirements", "non-functional requirements"])), 1))

# --- ad parsing -----------------------------------------------------------
parsed = parse_ad("company: ELMO\nrole: AI Analyst\nsource: http://x\n---\nAd body here")
results.append(check("header parsed", (parsed.company, parsed.role, parsed.source),
                     ("ELMO", "AI Analyst", "http://x")))
results.append(check("BOM tolerated",
                     parse_ad("﻿company: ELMO\nrole: BA\n---\nbody").company, "ELMO"))

# --- skills fit -----------------------------------------------------------
PROFILE = SkillProfile({
    "levels": {"strong": 1.0, "some": 0.5, "none": 0.0},
    "skills": [
        {"name": "SQL", "level": "strong", "evidence": "repo: sales-dashboard", "phrases": ["sql"]},
        {"name": "Power BI", "level": "some", "phrases": ["power bi"]},
        {"name": "Excel", "level": "none", "phrases": ["advanced excel", "in excel"]},
        {"name": "Python", "level": "strong", "phrases": ["python"]},
    ],
})
fit = PROFILE.match(ad("Data Analyst", "Strong SQL, Power BI and advanced Excel."))
results.append(check("skills fit averages levels of skills asked", fit.score, 50))
results.append(check("skills fit quotes evidence", [str(h) for h in fit.have], ['SQL "SQL" (repo: sales-dashboard)']))
results.append(check("skills fit lists missing", [str(m) for m in fit.missing], ['Excel "advanced Excel"']))
results.append(check("unasked skills ignored", PROFILE.match(ad("Analyst", "SQL only.")).score, 100))
results.append(check("no known skills -> unknown", PROFILE.match(ad("Analyst", "Great team.")).score, None))
results.append(check("'excel in your role' is not Excel",
                     PROFILE.match(ad("Analyst", "Support to excel in your role.")).score, None))

# --- contact searches -----------------------------------------------------
results.append(check("company suffix dropped", search_name("SJ Transport Service Pty Ltd"), "SJ Transport Service"))
results.append(check("board suffix dropped", search_name("Veolia | Australia & New Zealand"), "Veolia"))
results.append(check("real name words kept", search_name("Virgin Australia"), "Virgin Australia"))
MIX = [{"role": "analyst", "search": "analyst"}, {"role": "manager"}]
links = search_links("HUB24 Limited", MIX)
results.append(check("one search per group with a word, then everyone",
                     [label for label, _ in links], ["Analysts at HUB24", "Everyone at HUB24"]))
results.append(check("no company page: plain people search", links[0][1],
                     "https://www.linkedin.com/search/results/people/?keywords=HUB24+analyst"))
links = search_links("HUB24 Limited", MIX, "https://au.linkedin.com/company/hub24")
results.append(check("company page: its People tab, filtered", links[0][1],
                     "https://www.linkedin.com/company/hub24/people/?keywords=analyst"))
results.append(check("everyone: People tab unfiltered", links[1][1],
                     "https://www.linkedin.com/company/hub24/people/"))

# --- research brief -> Notion ---------------------------------------------
blocks = markdown_blocks("## Snapshot\n- **Bold** and [ASX](https://asx.com.au)\n> Hi James\n1. first\n\n"
                         "- https://example.com/a (secondary)")
results.append(check("brief block types", [b["type"] for b in blocks],
                     ["heading_3", "bulleted_list_item", "quote", "numbered_list_item", "bulleted_list_item"]))
results.append(check("markdown link kept", blocks[1]["bulleted_list_item"]["rich_text"][2]["text"]["link"],
                     {"url": "https://asx.com.au"}))
results.append(check("bare address becomes a link",
                     blocks[4]["bulleted_list_item"]["rich_text"][0]["text"].get("link"),
                     {"url": "https://example.com/a"}))
Block = type("Block", (), {})
ok, bad = Block(), Block()
ok.type = bad.type = "web_search_tool_result"
ok.content, bad.content = [1, 2], Block()
bad.content.error_code = "max_uses_exceeded"
results.append(check("search results and errors counted", _search_outcomes([ok, bad]), (2, ["max_uses_exceeded"])))

# --- a job saved by hand --------------------------------------------------
manual = from_ad(parse_ad("company: Acme Pty Ltd\nrole: Strategy Analyst\n"
                          "linkedin: https://www.linkedin.com/company/acme\n---\nWe need an analyst."))
results.append(check("manual job key", manual["key"], "manual:acme-pty-ltd-strategy-analyst"))
results.append(check("manual job matches a pulled one by company + role", manual["dedupe_key"],
                     "acme-pty-ltd|strategy-analyst"))
results.append(check("manual job keeps the LinkedIn page for contact search",
                     manual["company_research"]["linkedin"], "https://www.linkedin.com/company/acme"))

# --- a job added from a link ----------------------------------------------
results.append(check("ad HTML becomes plain text",
                     html_text("<p>About&nbsp;us</p><ul><li>SQL</li><li></li><li>Excel</li></ul><script>x()</script>"),
                     "About us\n\n- SQL\n- Excel"))
results.append(check("Seek job id from a search page",
                     _job_id("https://www.seek.com.au/analyst-jobs?jobId=123", r"/job/(\d+)", "jobId"), "123"))
results.append(check("LinkedIn job id from a titled link",
                     _job_id("https://au.linkedin.com/jobs/view/analyst-at-acme-4467432636?trk=x",
                             r"/jobs/view/(?:[^/]*-)?(\d+)", "currentJobId"), "4467432636"))
results.append(check("JobPosting found inside @graph",
                     [p["title"] for p in _job_postings({"@graph": [{"@type": "WebSite"},
                                                                    {"@type": "JobPosting", "title": "Analyst"}]})],
                     ["Analyst"]))
results.append(check("salary range in dollars", _salary(
    {"currency": "AUD", "value": {"minValue": 80000, "maxValue": 95000, "unitText": "YEAR"}}),
    "$80,000–$95,000 per year"))
old_date = (date.today() - timedelta(days=45)).isoformat()
results.append(check("job posted 45 days ago is too old", too_old({"posted": old_date}), 45))
results.append(check("job posted 30 days ago is kept",
                     too_old({"posted": (date.today() - timedelta(days=30)).isoformat()}), None))
results.append(check("job with no posting date is kept", too_old({"posted": ""}), None))
results.append(check("old job added from a link is kept", too_old({"posted": old_date, "added_from_link": True}), None))

# --- is the ad still open? ------------------------------------------------
results.append(check("closed wording spotted",
                     bool(_CLOSED_WORDS.search("Sorry, this job is no longer available.")), True))
results.append(check("live ad about filling in a form is not closed",
                     bool(_CLOSED_WORDS.search("Once the application form has been filled out, we'll call.")), False))
results.append(check("closed job gives its reason",
                     closed({"ad_status": {"state": "closed", "why": "Seek lists it as expired"}}),
                     "Seek lists it as expired"))
results.append(check("unknown is not closed", closed({"ad_status": {"state": "unknown", "why": "blocked"}}), None))
today = date.today().isoformat()
results.append(check("ad checked today is skipped", due({"ad_status": {"state": "open", "checked": today}}, False), False))
results.append(check("ad never checked is due", due({}, False), True))
results.append(check("closed ad isn't re-checked unless asked",
                     (due({"ad_status": {"state": "closed", "checked": "2026-01-01"}}, False),
                      due({"ad_status": {"state": "closed", "checked": "2026-01-01"}}, True)), (False, True)))

# --- people named in a research brief -------------------------------------
brief_md = ("## Snapshot\n- Makes software.\n## Who to send it to\n"
            "- **Jo Lee**, Head of Finance — owns the pain point. [source](https://acme.com/team)\n"
            "- **Sam Ng**, Data Analyst — ask which team the role sits in.\n"
            "## Opening line\nHi Jo")
results.append(check("people pulled out of the brief", people_from(brief_md),
                     "Jo Lee, Head of Finance — owns the pain point. source (https://acme.com/team)\n"
                     "Sam Ng, Data Analyst — ask which team the role sits in."))
results.append(check("no people section, nothing pulled", people_from("## Snapshot\n- x"), ""))

# --- LinkedIn connections -------------------------------------------------
export = Path(tempfile.mkdtemp()) / "Connections.csv"
export.write_text('Notes:\n"When exporting your connection data, you may notice..."\n\n'
                  "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
                  "Jo,Lee,https://www.linkedin.com/in/jolee,,Deloitte Australia,Analyst,01 Jan 2026\n"
                  "Sam,Ng,,,Commonwealth Bank,Data Analyst,02 Jan 2026\n"
                  "Ana,Roy,,,Hays Travel,Agent,03 Jan 2026\n"
                  "No,Company,,,,,04 Jan 2026\n", encoding="utf-8")
known = connections.index(connections.load(export))
results.append(check("export read past the Notes lines", sum(len(v) for v in known.values()), 3))
results.append(check("company filler words dropped", connections.company_key("Deloitte Pty Ltd"), "deloitte"))
results.append(check("connection matched despite 'Australia'",
                     [p["name"] for p in connections.known_at("Deloitte", known)], ["Jo Lee"]))
results.append(check("two-word name matches a longer one",
                     [p["name"] for p in connections.known_at("Commonwealth Bank of Australia", known)], ["Sam Ng"]))
results.append(check("one-word name doesn't match a longer one", connections.known_at("Hays", known), []))

results.append(check("foreign salary is not read as dollars",
                     parse_salary("Salary: " + _salary({"currency": "EUR", "value": {"value": 90000}})), None))

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
