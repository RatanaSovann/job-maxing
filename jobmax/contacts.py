"""People to connect with, per company.

Keyed by company, not by job: Hays advertises four roles, and that is still one
set of people to know. Results are cached in data/contacts.json, so re-running
after a new pull only pays for companies that are genuinely new.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from .apify import PullError, run_actor
from .store import DATA

ACTOR = "harvestapi/linkedin-company-employees"
CONTACTS = DATA / "contacts.json"

# The actor's own pricing labels, which double as the mode names it accepts.
MODES = {
    "profile": ("Short ($4 per 1k)", 0.004),
    "email": ("Full + email search ($12 per 1k)", 0.012),
}
START_COST = 0.02
# Apify rejects a run whose cost cap is under this.
MIN_RUN_COST = 0.05


def load(path: Path = CONTACTS) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(data: dict, path: Path = CONTACTS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def search_name(company: str) -> str:
    """The company name as people write it on LinkedIn.

    'Veolia | Australia & New Zealand' -> 'Veolia'
    'SJ Transport Service Pty Ltd'     -> 'SJ Transport Service'
    """
    name = re.split(r"\s[|—–]\s", company)[0]
    name = re.sub(r"\b(pty|ltd|limited)\b\.?", "", name, flags=re.IGNORECASE)
    return " ".join(name.split())


def search_links(company: str, mix: list[dict], company_url: str = "") -> list[tuple[str, str]]:
    """(label, url) LinkedIn searches: one per contact group with a `search` word, then everyone.

    With the company's LinkedIn page, this is its People tab filtered by the
    word: current staff only. Without one (Seek), a plain people search on
    name + word. One plain word each: LinkedIn returns nothing for long
    boolean queries or a quoted name that profiles don't spell exactly.

    Free, and nothing is scraped: you open the search and pick people yourself.
    """
    name = search_name(company)
    slug = company_url.rstrip("/").split("/company/")[-1] if "/company/" in company_url else ""

    def url(word: str) -> str:
        if slug:
            base = f"https://www.linkedin.com/company/{slug}/people/"
            return base + (f"?{urllib.parse.urlencode({'keywords': word})}" if word else "")
        return ("https://www.linkedin.com/search/results/people/?"
                + urllib.parse.urlencode({"keywords": f"{name} {word}".strip()}))

    links = [(f'{group["role"].capitalize()}s at {name}', url(group["search"]))
             for group in mix if group.get("search")]
    return links + [(f"Everyone at {name}", url(""))]


def company_link(job: dict) -> str:
    """The company's LinkedIn page, tracking junk removed. Also the contacts.json key."""
    return (job.get("company_research") or {}).get("linkedin", "").split("?")[0]


def companies_from_jobs(jobs: list[dict]) -> dict[str, dict]:
    """One entry per company that has a LinkedIn page, with its jobs listed."""
    companies: dict[str, dict] = {}
    for job in jobs:
        url = company_link(job)
        if not url:
            continue
        entry = companies.setdefault(url, {
            "company": job["company"],
            "linkedin": url,
            "website": (job.get("company_research") or {}).get("website", ""),
            "is_agency": is_agency(job),
            "roles": [],
        })
        entry["roles"].append(job["role"])
    return companies


def is_agency(job: dict) -> bool:
    """Recruitment agencies advertise other companies' jobs.

    Worth knowing before building an artifact: an agency has no pain point of
    its own to solve, and the hiring manager works somewhere else.

    LinkedIn says so in the company's industry; Seek gives no industry, so the
    company name is checked too ("GWG Recruitment", "Randstad Professionals").
    """
    research = job.get("company_research") or {}
    haystack = f"{research.get('industries', '')} {research.get('sector', '')} {job.get('company', '')}".lower()
    return any(word in haystack for word in
               ("staffing", "recruit", "employment agency", "personnel", "randstad", "hays"))


def _person(item: dict, wanted_role: str) -> dict:
    position = (item.get("currentPositions") or [{}])[0]
    location = item.get("location") or {}
    emails = item.get("emails") or item.get("email") or ""
    if isinstance(emails, list):
        emails = ", ".join(str(e) for e in emails if e)
    return {
        "name": " ".join(p for p in (item.get("firstName"), item.get("lastName")) if p).strip(),
        "title": (position.get("position") or position.get("title")
                  or position.get("description", "").split("\n")[0][:90]).strip(),
        "company": (position.get("companyName") or "").strip(),
        "linkedin": (item.get("linkedinUrl") or "").strip(),
        "location": (location.get("linkedinText") or "").strip() if isinstance(location, dict) else "",
        "email": str(emails).strip(),
        "open_profile": bool(item.get("openProfile")),
        "targeted_as": wanted_role,
        "summary": (item.get("summary") or "").strip()[:220],
    }


def fetch_for_companies(
    companies: list[dict], mix: list[dict], token: str,
    mode: str = "profile", exclude: list[str] | None = None,
    on_status=None,
) -> tuple[dict[str, list[dict]], float]:
    """Fetch the wanted mix of people, one actor run per company per role group.

    Companies whose lookups all failed are missing from the result.

    Batching many companies into a single run was tried first and failed badly:
    asked for 60 managers across 15 companies, LinkedIn returned almost all of
    them from the two giants (Tata ~600k staff, HCLTech ~200k) and 13 companies
    got nobody. Size dominates the result order, and the small companies are
    exactly the ones worth contacting.

    So each company gets its own run. That costs a $0.02 start fee per run
    (~$0.05 per company for 2 managers + 1 analyst) and guarantees the mix.
    Because it is priced per company, look up a shortlist, not everything —
    `--min-score`, and agencies are skipped by default.
    """
    mode_name, per_person = MODES[mode]
    by_company: dict[str, list[dict]] = {}
    spent = 0.0

    for index, company in enumerate(companies, start=1):
        found: list[dict] = []
        succeeded = False
        if on_status:
            on_status(f"[{index}/{len(companies)}] {company['company']}")

        for group in mix:
            wanted = int(group.get("wanted", 1))
            titles = group.get("titles", [])
            if not (wanted and titles):
                continue

            # One spare, so a single excluded title does not leave a gap.
            ask = wanted + 1
            try:
                items, cost = run_actor(
                    ACTOR,
                    {
                        "companies": [company["linkedin"]],
                        "jobTitles": titles,
                        "profileScraperMode": mode_name,
                        "maxItems": ask,
                    },
                    token,
                    max_items=ask,
                    max_cost_usd=max(MIN_RUN_COST,
                                     round(START_COST + ask * per_person + 0.02, 4)),
                )
            except PullError as err:
                # One company failing must not lose the companies already done.
                print(f"    {group['role']} lookup failed: {err}")
                continue

            succeeded = True
            spent += cost or 0.0
            for item in items:
                person = _person(item, group["role"])
                if _excluded(person["title"], exclude):
                    continue
                if len(_of_role(found, group["role"])) < wanted:
                    found.append(person)

        # Every lookup failed: leave this company out, so its cached people survive.
        if succeeded:
            by_company[company["linkedin"]] = found

    return by_company, spent


def _excluded(title: str, exclude: list[str] | None) -> bool:
    lowered = (title or "").lower()
    return any(word.lower() in lowered for word in (exclude or []))


def _of_role(people: list[dict], role: str) -> list[dict]:
    return [p for p in people if p.get("targeted_as") == role]


def _slug(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def estimate(company_count: int, mix: list[dict], mode: str = "profile") -> float:
    """One run per company per role group, each asking for one spare person."""
    per_person = MODES[mode][1]
    groups = [g for g in mix if g.get("wanted") and g.get("titles")]
    per_company = len(groups) * START_COST + sum(int(g["wanted"]) + 1 for g in groups) * per_person
    return company_count * per_company


def record(company: dict, people: list[dict], mode: str) -> dict:
    return {
        **company,
        "people": people,
        "mode": mode,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
