"""Where pulled jobs live.

    data/raw/linkedin-20260926-1903.json   exactly what the actor returned
    data/jobs.json                         the de-duplicated job store

The raw file is the audit trail: if a score looks wrong, the untouched source
data is still there. The store is what everything downstream reads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
STORE = DATA / "jobs.json"


@dataclass
class MergeReport:
    added: list[dict]
    seen_before: list[dict]
    duplicates_in_pull: list[dict]
    unusable: int

    @property
    def total(self) -> int:
        return len(self.added) + len(self.seen_before) + len(self.duplicates_in_pull) + self.unusable


def save_raw(source: str, items: list[dict]) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"{source}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def load(path: Path = STORE) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8-sig"))


def merge(records: list[dict], path: Path = STORE, unusable: int = 0) -> MergeReport:
    """Add new jobs to the store, skipping ones already there.

    Two jobs are the same if they share the board's own id, or if the same
    company advertises the same role title twice (a repost, or the same job
    later pulled from a second board).
    """
    existing = load(path)
    keys = {job["key"] for job in existing}
    fuzzy = {job.get("dedupe_key") for job in existing}

    report = MergeReport([], [], [], unusable)
    for record in records:
        if record["key"] in keys:
            report.seen_before.append(record)
        elif record.get("dedupe_key") in fuzzy:
            report.duplicates_in_pull.append(record)
        else:
            keys.add(record["key"])
            fuzzy.add(record.get("dedupe_key"))
            record["first_seen"] = record["pulled_at"]
            report.added.append(record)

    if report.added:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(existing + report.added, indent=1, ensure_ascii=False)
        # Write to a temp file then replace, so an interrupted write cannot
        # destroy jobs already collected.
        temp = path.with_suffix(".json.tmp")
        temp.write_text(payload, encoding="utf-8")
        temp.replace(path)

    return report


def coverage(records: list[dict]) -> list[tuple[str, int, int]]:
    """How often each field the rubric depends on was actually populated."""
    checks = {
        "employment type": lambda r: "Employment type:" in r["description"],
        "salary": lambda r: "Salary:" in r["description"],
        "location": lambda r: bool(r.get("location")),
        "job url": lambda r: bool(r.get("url")),
        "posted date": lambda r: bool(r.get("posted")),
        "recruiter name": lambda r: bool((r.get("recruiter") or {}).get("name")),
        "company website": lambda r: bool((r.get("company_research") or {}).get("website")),
        "company about": lambda r: bool((r.get("company_research") or {}).get("about")),
    }
    total = len(records)
    return [(name, sum(1 for r in records if test(r)), total) for name, test in checks.items()]
