"""People you already know: your LinkedIn connections, matched to the companies in your job list.

LinkedIn lets you download your own connections: Settings → Data privacy → Get a copy
of your data → Connections. Save the file as data/Connections.csv. Nothing is scraped
and nothing is sent anywhere; this only reads that file.

It lives in data/ so it is never committed: it holds other people's details.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from .contacts import search_name
from .store import DATA

CONNECTIONS = DATA / "Connections.csv"

# Words people add or drop when they type their employer: "Deloitte Australia", "Macquarie Group".
_FILLER = {"australia", "aus", "anz", "nz", "new", "zealand", "group", "holdings", "limited", "ltd",
           "pty", "inc", "the", "and", "co", "company", "corporation", "corp", "plc", "au"}


def company_key(name: str) -> str:
    """'Deloitte Australia' and 'Deloitte' → 'deloitte'. Empty if nothing distinctive is left."""
    words = re.sub(r"[^a-z0-9 ]+", " ", search_name(name).lower().replace("&", " and ")).split()
    return " ".join(w for w in words if w not in _FILLER)


def load(path: Path = CONNECTIONS) -> list[dict]:
    """Your connections, or [] if you haven't saved the export yet.

    The export starts with a few "Notes:" lines before the real header, and
    LinkedIn has changed how many, so the header is found by its column names.
    """
    if not path.exists():
        return []
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    start = next((i for i, row in enumerate(rows) if "First Name" in row and "Company" in row), None)
    if start is None:
        raise ValueError(f"{path.name} has no 'First Name' / 'Company' header. "
                         "Is it the Connections.csv file from LinkedIn's data export?")
    header = rows[start]
    people = []
    for row in rows[start + 1:]:
        cell = dict(zip(header, row))
        name = f'{cell.get("First Name", "")} {cell.get("Last Name", "")}'.strip()
        company = (cell.get("Company") or "").strip()
        if name and company:
            people.append({"name": name, "company": company,
                           "position": (cell.get("Position") or "").strip(),
                           "linkedin": (cell.get("URL") or "").strip()})
    return people


def index(people: list[dict]) -> dict[str, list[dict]]:
    by_company: dict[str, list[dict]] = {}
    for person in people:
        if key := company_key(person["company"]):
            by_company.setdefault(key, []).append(person)
    return by_company


def known_at(company: str, by_company: dict[str, list[dict]]) -> list[dict]:
    """Connections who work at this company.

    Same name once filler words are dropped, or one name starting the other when
    the shorter is at least two words ("Commonwealth Bank" / "Commonwealth Bank of
    Australia"). One-word prefixes are too loose: "Hays" would match "Hays Travel".
    Each person keeps the employer they typed, so you can check the match.
    """
    key = company_key(company)
    if not key:
        return []
    found = list(by_company.get(key, []))
    for other, people in by_company.items():
        if other == key:
            continue
        short, long = sorted((key, other), key=len)
        if len(short.split()) >= 2 and long.startswith(short + " "):
            found += people
    return found


def as_text(people: list[dict]) -> str:
    """One line per person, for the research prompt."""
    return "\n".join(f'- {p["name"]}, {p["position"] or "position not listed"} '
                     f'(their LinkedIn says: {p["company"]})' for p in people)
