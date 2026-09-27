"""A job from a link you paste: fetch the ad page and turn it into a store record.

Free: one ordinary page fetch, no Apify. Three ways to read a page, tried in order:

    Seek        the job data Seek embeds in its own page       -> same record as a Seek pull
    LinkedIn    LinkedIn's public (logged-out) view of one job -> same record as a LinkedIn pull
    Anything    the schema.org "JobPosting" block most career sites publish for Google Jobs
    else        (Workday, Greenhouse, Lever, SmartRecruiters, ...) -> board "manual"

Seek and LinkedIn links get the board's own id, so pasting a job that a pull later
finds (or already found) is recognised as the same job.
"""

from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from .ads import Ad
from .sources import LINKEDIN, SEEK, facts_block, from_ad

# A normal browser's User-Agent: some boards refuse Python's default one.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "en-AU,en;q=0.9",
}
MAX_BYTES = 8_000_000


class LinkError(ValueError):
    pass


# --- HTML to plain text ------------------------------------------------------

_BLOCKS = {"p", "div", "br", "ul", "ol", "tr", "section", "h1", "h2", "h3", "h4", "h5", "h6"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0  # inside <script>/<style>

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        elif tag in _BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def html_text(html: str) -> str:
    """Readable text from an HTML fragment: one paragraph per line, list items as "- "."""
    parser = _Text()
    parser.feed(html)
    parser.close()
    lines = [re.sub(r"[ \t\r\f\v\xa0]+", " ", line).strip() for line in "".join(parser.parts).split("\n")]
    text = "\n".join(line for line in lines if line != "-")  # "-" alone: an empty <li>
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --- fetching ----------------------------------------------------------------

def _get(url: str) -> tuple[str, str]:
    """(address after redirects, page text)."""
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=25) as response:
            body = response.read(MAX_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            return response.geturl(), body.decode(charset, errors="replace")
    except HTTPError as err:
        raise LinkError(f"{urlsplit(url).netloc} answered {err.code} ({err.reason}).") from None
    except (URLError, TimeoutError, OSError) as err:
        raise LinkError(f"could not reach {urlsplit(url).netloc}: {getattr(err, 'reason', err)}") from None


def _job_id(url: str, path_pattern: str, query_key: str) -> str:
    parts = urlsplit(url)
    if m := re.search(path_pattern, parts.path):
        return m.group(1)
    value = parse_qs(parts.query).get(query_key, [""])[0]
    return value if value.isdigit() else ""


# --- Seek --------------------------------------------------------------------

def _seek(url: str) -> dict:
    # A job page (/job/123) or a search page with a job open (?jobId=123).
    job_id = _job_id(url, r"/job/(\d+)", "jobId")
    if not job_id:
        raise LinkError("that Seek link doesn't point at one job. Open the ad and copy its address.")
    parts = urlsplit(url)
    page_url, page = _get(f"{parts.scheme}://{parts.netloc}/job/{job_id}")

    m = re.search(r"window\.SEEK_REDUX_DATA\s*=\s*(\{.*?\});?\s*\n", page, re.S)
    if not m:
        raise LinkError("Seek's page didn't include the job details (the page layout may have changed).")
    try:
        data = json.loads(m.group(1).replace(":undefined", ":null"))
        result = data["jobdetails"]["result"]
        job = result["job"]
    except (ValueError, KeyError, TypeError):
        raise LinkError("Seek's page didn't include the job details (it may have expired).") from None

    tracking = ((job.get("tracking") or {}).get("classificationInfo") or {})
    item = {  # the field names the Seek actor uses, so the same reader builds the record
        "title": job.get("title"),
        "company": (job.get("advertiser") or {}).get("name"),
        "description": html_text(job.get("content") or ""),
        "employmentType": (job.get("workTypes") or {}).get("label"),
        "workArrangement": (result.get("workArrangements") or {}).get("label"),
        "salaryText": (job.get("salary") or {}).get("label"),
        "category": tracking.get("classification"),
        "subCategory": tracking.get("subClassification"),
        "seekJobId": job.get("id") or job_id,
        "location": (job.get("location") or {}).get("label"),
        "canonicalUrl": page_url.split("?")[0],
        "postedDate": (job.get("listedAt") or {}).get("dateTimeUtc") or "",
    }
    record = SEEK.to_record(item)
    if not record:
        raise LinkError("Seek's page had no title, company or description for this job.")
    return record


# --- LinkedIn ----------------------------------------------------------------

def _between(html: str, pattern: str) -> str:
    m = re.search(pattern, html, re.S)
    return html_text(m.group(1)) if m else ""


def _linkedin(url: str) -> dict:
    # /jobs/view/4467432636, /jobs/view/some-title-at-company-4467432636, or ?currentJobId=4467432636
    job_id = _job_id(url, r"/jobs/view/(?:[^/]*-)?(\d+)", "currentJobId")
    if not job_id:
        raise LinkError("that LinkedIn link doesn't point at one job. Open the ad and copy its address.")
    _, page = _get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}")

    criteria = {html_text(k): html_text(v) for k, v in re.findall(
        r'job-criteria-subheader[^>]*>(.*?)</h3>\s*<span[^>]*>(.*?)</span>', page, re.S)}
    company = re.search(r'topcard__org-name-link[^>]*href="([^"]*)"[^>]*>(.*?)</a>', page, re.S)
    item = {  # the field names the LinkedIn actor uses, so the same reader builds the record
        "id": job_id,
        "title": _between(page, r'top-card-layout__title[^>]*>(.*?)</h'),
        "companyName": html_text(company.group(2)) if company else "",
        "companyUrl": unescape(company.group(1)).split("?")[0] if company else "",
        "description": _between(page, r'show-more-less-html__markup[^>]*>(.*?)</section>'),
        "location": _between(page, r'topcard__flavor--bullet[^>]*>(.*?)</span>'),
        "salary": _between(page, r'compensation__salary[^>]*>(.*?)</div>'),
        "contractType": criteria.get("Employment type"),
        "experienceLevel": criteria.get("Seniority level"),
        "jobFunction": criteria.get("Job function"),
        "companyIndustries": criteria.get("Industries"),
        "postedTime": _between(page, r'posted-time-ago__text[^>]*>(.*?)</span>'),
        "jobUrl": f"https://www.linkedin.com/jobs/view/{job_id}",
    }
    record = LINKEDIN.to_record(item)
    if not record:
        raise LinkError("LinkedIn didn't show this job to a logged-out visitor (it may have closed).")
    return record


# --- any other site: schema.org JobPosting -----------------------------------

def _job_postings(value):
    """Every JobPosting object in a JSON-LD value (they can sit in lists or an @graph)."""
    if isinstance(value, list):
        for v in value:
            yield from _job_postings(v)
    elif isinstance(value, dict):
        kind = value.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            yield value
        yield from _job_postings(value.get("@graph"))


def _name(value) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = value.get("name", "")
    return str(value or "").strip()


def _salary(value) -> str:
    """'$80,000–$95,000 per year' from a schema.org MonetaryAmount.

    Other currencies keep their code ('EUR 89,100'), which the scorer doesn't read
    as dollars, so the salary counts as unknown rather than wrongly converted.
    """
    if not isinstance(value, dict):
        return str(value or "")
    currency = str(value.get("currency") or "AUD").upper()
    sign = "$" if currency == "AUD" else currency + " "
    amount = value.get("value")
    if not isinstance(amount, dict):
        amount = {"value": amount}
    numbers = []
    for key in ("minValue", "maxValue", "value"):
        try:
            numbers.append(f"{sign}{float(amount.get(key)):,.0f}")
        except (TypeError, ValueError):
            pass
    unit = str(amount.get("unitText") or "").lower()
    return "–".join(dict.fromkeys(numbers)) + (f" per {unit}" if numbers and unit else "")


def _place(value) -> str:
    if isinstance(value, list):
        value = value[0] if value else {}
    address = (value or {}).get("address") if isinstance(value, dict) else None
    if isinstance(address, dict):
        return ", ".join(filter(None, (str(address.get(k) or "").strip()
                                       for k in ("addressLocality", "addressRegion"))))
    return str(address or "")


def _structured(url: str) -> dict:
    page_url, page = _get(url)
    posting = None
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            posting = next(_job_postings(json.loads(block.strip())), None)
        except ValueError:
            continue
        if posting:
            break
    if not posting:
        raise LinkError("this page has no job details a program can read. Copy the ad into a text "
                        "file instead and use: python -m commands.research --ad FILE")

    description = str(posting.get("description") or "")
    if "&lt;" in description:  # some sites escape the HTML twice
        description = unescape(description)
    types = posting.get("employmentType")
    types = ", ".join(types) if isinstance(types, list) else str(types or "")
    facts = facts_block([
        ("Employment type", types.replace("_", " ").capitalize()),
        ("Salary", _salary(posting.get("baseSalary"))),
    ])
    organisation = posting.get("hiringOrganization")
    ad = Ad(
        company=_name(organisation),
        role=str(posting.get("title") or "").strip(),
        description=facts + html_text(description),
        source=page_url,
        location=_place(posting.get("jobLocation")),
        extra={"posted": str(posting.get("datePosted") or "")[:10],
               "website": organisation.get("sameAs", "") if isinstance(organisation, dict) else ""},
    )
    if not (ad.company and ad.role and html_text(description)):
        raise LinkError("the job details on this page are missing the company, title or description.")
    return from_ad(ad)


def from_link(url: str) -> dict:
    """A store record for the job ad at this address. Raises LinkError, in plain words, if it can't."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise LinkError("that isn't a web address. Copy the whole link, starting with https://")
    host = parts.netloc.lower()
    if "seek.com" in host:
        return _seek(url)
    if host.endswith("linkedin.com"):
        return _linkedin(url)
    return _structured(url)
