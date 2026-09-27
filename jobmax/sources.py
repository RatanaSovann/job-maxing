"""Job sources: how to ask an Apify actor for jobs, and how to read its answer.

One entry per source. Adding Seek or Indeed later means adding an entry here
and nothing else — the store, the scorer and the dashboard never learn which
board a job came from.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .scorer import find


def _text(value) -> str:
    """Any JSON value as trimmed text. The board sends numbers as ints sometimes
    (companyEmployeeCount) and as strings other times."""
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def facts_block(pairs: list[tuple[str, str]]) -> str:
    """The structured fields the board gave us, written into the scored text.

    The scorer reads text, so a field like contractType="Full-time" only counts
    if it appears in the text. Writing it in a labelled block keeps one code
    path in the scorer and keeps the quotes on the job card honest.
    """
    lines = [f"{label}: {value}" for label, value in pairs if str(value or "").strip()]
    if not lines:
        return ""
    return "Job facts (from the job board):\n" + "\n".join(lines) + "\n\n"


@dataclass
class Search:
    """What to ask a board for. Filled from `search:` in the goal file."""
    titles: list[str]
    location: str
    rows: int
    experience_levels: list[str] = field(default_factory=list)
    # Words that mark a job title as too senior. Boards that can filter on
    # their side get them in the request (dropped jobs cost nothing); every
    # board's results are also checked by `too_senior()` after the pull.
    exclude_title_words: list[str] = field(default_factory=list)


MAX_AGE_DAYS = 30  # the boards are asked for this window too; Seek's nearest option is 31 days


def too_old(job: dict) -> int | None:
    """How many days ago the job was posted, if that is more than MAX_AGE_DAYS.

    None when it is recent, has no posting date (unknown is not old), or was
    added from a link (you picked it, so it stays whatever its age).
    """
    if job.get("added_from_link"):
        return None
    try:
        days = (datetime.now().date() - datetime.fromisoformat(job.get("posted", "")[:10]).date()).days
    except ValueError:
        return None
    return days if days > MAX_AGE_DAYS else None


def too_senior(role: str, words: list[str]) -> str | None:
    """The first exclude word found in a job title.

    Same matching as the rubric: whole words, and "senior*" also catches
    "SeniorBusiness Analyst".
    """
    hits = find(role, words)
    return hits[0].phrase if hits else None


@dataclass
class Source:
    name: str
    actor: str
    price_per_item_usd: float
    build_input: Callable[[Search], dict]
    to_record: Callable[[dict], dict | None]
    price_per_run_usd: float = 0.0


# --------------------------------------------------------------------------
# LinkedIn Jobs — bebity/linkedin-jobs-scraper
# --------------------------------------------------------------------------
# Chosen because it is the cheapest per job of the actors surveyed, needs no
# LinkedIn cookie of ours, and returns the recruiter plus company details that
# Stage 6 (contacts) and Stage 7 (research) would otherwise have to pay for.

_LINKEDIN_LEVELS = {
    "internship": "1",
    "entry level": "2",
    "associate": "3",
    "mid-senior level": "4",
    "director": "5",
}


def _linkedin_input(search: Search) -> dict:
    # LinkedIn has no "exclude words" option; senior titles are dropped after
    # the pull, so they are still paid for.
    levels = search.experience_levels
    unknown = [lv for lv in levels if lv.lower() not in _LINKEDIN_LEVELS]
    if unknown:
        raise ValueError(f"Unknown experience level {unknown}. "
                         f"LinkedIn has: {', '.join(k.capitalize() for k in _LINKEDIN_LEVELS)}")
    request = {
        "titles": search.titles,
        "locations": [search.location],
        "rows": search.rows,
        "publishedAt": "r2592000",  # last 30 days
    }
    if levels:
        request["experienceLevels"] = [_LINKEDIN_LEVELS[lv.lower()] for lv in levels]
    return request


def _linkedin_record(item: dict) -> dict | None:
    role = _text(item.get("title"))
    company = _text(item.get("companyName"))
    description = _text(item.get("description"))
    if not (role and company and description):
        return None

    facts = facts_block([
        ("Employment type", item.get("contractType")),
        ("Work type", item.get("workType")),
        ("Salary", item.get("salary")),
        ("Experience level", item.get("experienceLevel")),
        ("Job function", item.get("jobFunction")),
    ])

    source_id = _text(item.get("id"))
    return {
        "key": f"linkedin:{source_id}" if source_id else f"linkedin:{_slug(company)}-{_slug(role)}",
        "dedupe_key": f"{_slug(company)}|{_slug(role)}",
        "source": "linkedin",
        "source_id": source_id,
        "company": company,
        "role": role,
        "location": _text(item.get("location")),
        "url": _text(item.get("jobUrl")),
        "apply_url": _text(item.get("applyUrl")),
        "posted": _text(item.get("publishedAt")),
        "posted_text": _text(item.get("postedTime")),
        "applicants": _text(item.get("applicationsCount")),
        # What the scorer reads. The company blurb is deliberately left out: a
        # marketing line like "we serve government clients" would otherwise
        # trip the government knockout.
        "description": facts + description,
        "recruiter": {
            "name": _text(item.get("posterFullName")),
            "profile": _text(item.get("posterProfileUrl")),
        },
        "company_research": {
            "linkedin": _text(item.get("companyUrl")),
            "website": _text(item.get("companyWebsite")),
            "industries": _text(item.get("companyIndustries")),
            "sector": _text(item.get("sector")),
            "size": _text(item.get("companySize")),
            "employees": _text(item.get("companyEmployeeCount")),
            "type": _text(item.get("companyType")),
            "founded": _text(item.get("companyFoundedYear")),
            "headquarters": _text(item.get("companyHeadquartersText")),
            "about": _text(item.get("companyDescription")),
        },
        "pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


LINKEDIN = Source(
    name="linkedin",
    actor="bebity/linkedin-jobs-scraper",
    price_per_item_usd=0.0015,
    build_input=_linkedin_input,
    to_record=_linkedin_record,
)

# --------------------------------------------------------------------------
# Seek — blackfalcondata/seek-scraper
# --------------------------------------------------------------------------
# Chosen because it can drop senior titles on Seek's side before they are
# charged, and returns the full description, salary and employment type.
# Seek gives no LinkedIn company link, so contact lookup skips these jobs.

def _seek_input(search: Search) -> dict:
    request = {
        # The actor takes several searches as a JSON-encoded string, not a list.
        "query": json.dumps(search.titles),
        "country": "AU",
        # Seek's own name for the whole country is "All Australia".
        "location": "All Australia" if search.location.lower() == "australia" else search.location,
        "maxResults": search.rows,
        "dateRange": "31",
        "includeDetails": True,
        "descriptionFormat": "text",
    }
    if search.exclude_title_words:
        request["excludeKeywords"] = [w.rstrip("*") for w in search.exclude_title_words]
        request["keywordMatchTitle"] = True  # title only, not the description
    return request


def _seek_record(item: dict) -> dict | None:
    role = _text(item.get("title"))
    company = _text(item.get("company"))
    description = _text(item.get("description"))
    if not (role and company and description):
        return None

    category = " › ".join(filter(None, [_text(item.get("category")), _text(item.get("subCategory"))]))
    facts = facts_block([
        ("Employment type", item.get("employmentType")),
        ("Work type", item.get("workArrangement")),
        ("Salary", item.get("salaryText")),
        ("Seek category", category),
    ])

    source_id = _text(item.get("seekJobId"))
    return {
        "key": f"seek:{source_id}" if source_id else f"seek:{_slug(company)}-{_slug(role)}",
        "dedupe_key": f"{_slug(company)}|{_slug(role)}",
        "source": "seek",
        "source_id": source_id,
        "company": company,
        "role": role,
        "location": _text(item.get("location")),
        "url": _text(item.get("canonicalUrl")),
        "apply_url": _text(item.get("applyUrl")),
        "posted": _text(item.get("postedDate"))[:10],
        "posted_text": "",
        "applicants": _text(item.get("applicantCount")),
        "description": facts + description,
        # Seek hides the recruiter; a named contact is rare.
        "recruiter": {"name": _text(item.get("contactName")), "profile": ""},
        "company_research": {
            "linkedin": _text((item.get("socialProfiles") or {}).get("linkedin")),
            "website": _text(item.get("companyWebsite")),
            "industries": _text(item.get("companyIndustry")),
            "sector": category,
            "size": _text(item.get("companySize")),
            "employees": "",
            "type": "",
            "founded": "",
            "headquarters": "",
            "about": _text(item.get("companyDescription")),
        },
        "pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


SEEK = Source(
    name="seek",
    actor="blackfalcondata/seek-scraper",
    price_per_item_usd=0.002,
    price_per_run_usd=0.01,
    build_input=_seek_input,
    to_record=_seek_record,
)

SOURCES = {LINKEDIN.name: LINKEDIN, SEEK.name: SEEK}


def from_ad(ad) -> dict:
    """A job you saved by hand (an ad file, see fixtures/README.md) as a store record.

    Optional header lines `linkedin:` (the company's LinkedIn page) and
    `website:` feed contact search and research, like the boards' own fields.
    """
    extra = {k: _text(v) for k, v in ad.extra.items()}
    return {
        "key": f"manual:{_slug(ad.company)}-{_slug(ad.role)}",
        "dedupe_key": f"{_slug(ad.company)}|{_slug(ad.role)}",
        "source": "manual",
        "source_id": "",
        "company": ad.company,
        "role": ad.role,
        "location": ad.location,
        "url": ad.source,
        "apply_url": "",
        "posted": extra.get("posted", ""),
        "posted_text": "",
        "applicants": "",
        "description": ad.description,
        "recruiter": {"name": "", "profile": ""},
        "company_research": {"linkedin": extra.get("linkedin", ""), "website": extra.get("website", "")},
        "pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
