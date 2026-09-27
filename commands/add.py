"""Add a job to data/jobs.json from a link you paste.

    python -m commands.add https://www.seek.com.au/job/12345678
    python -m commands.add LINK LINK ...                several at once

Works with Seek, LinkedIn, and most company career sites (see jobmax/links.py).
Free: it reads the ad page directly, no Apify. The job is kept even if the
seniority filter, the 30-day age limit or the rules would skip it: you picked it.

This only adds to the list. To also send it to Notion and rebuild the job list page:
    python -m commands.refresh --add LINK        (or the "Add job" box on the page from app.py)
"""

import argparse
import sys
from pathlib import Path

from jobmax import store
from jobmax.ads import from_record
from jobmax.config import ROOT
from jobmax.links import LinkError, from_link
from jobmax.scorer import Rubric

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("links", nargs="+", help="job ad addresses")
    parser.add_argument("--goal", type=Path, default=ROOT / "goals" / "pr_australia.yaml")
    args = parser.parse_args(argv)

    rubric = Rubric.load(args.goal)
    failed = 0
    for link in args.links:
        print(f"Reading {link}")
        try:
            record = from_link(link)
        except LinkError as err:
            print(f"  Couldn't add it: {err}")
            failed += 1
            continue

        record["added_from_link"] = True
        report = store.merge([record])
        if not report.added:
            print(f"  Already in your list: {record['company']} — {record['role']}")
            continue
        result = rubric.score(from_record(record))
        verdict = (f"skipped by the rules ({result.knockouts[0][0]}), shown in the Skipped list"
                   if result.skipped else f"PR score {result.total} · {result.likely_code}")
        print(f"  Added ({record['source']}): {record['company']} — {record['role']}\n  {verdict}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
