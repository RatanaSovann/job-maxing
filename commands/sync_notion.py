"""Send scored jobs to the Notion tracker.

    python -m commands.sync_notion --dry-run     what it would add / update, writes nothing
    python -m commands.sync_notion               add new jobs, refresh scores on existing ones

Free. Knocked-out jobs are not sent (they stay on the dashboard's Skipped list),
and neither are jobs posted over 30 days ago. Rows already in Notion are kept
as they age, since you may be tracking them.
Your own columns (Status, Date applied, Outreach count, Research done,
Artifact status, Contacts) are only filled when a job is first added, never
overwritten after that.
"""

import argparse
import sys
from pathlib import Path

from jobmax import contacts, store
from jobmax.ads import from_record
from jobmax.config import MissingSecret, secret
from jobmax.notion import (Notion, NotionError, create_row, ensure_columns, missing_columns,
                           row_key, save_pages, tool_properties)
from jobmax.scorer import Rubric
from jobmax.skills import SkillProfile
from jobmax.sources import too_old

from jobmax.config import ROOT
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--goal", type=Path, default=ROOT / "goals" / "pr_australia.yaml")
    parser.add_argument("--profile", type=Path, default=ROOT / "profile" / "skills.yaml")
    parser.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    args = parser.parse_args()

    jobs = store.load()
    if not jobs:
        print("No jobs in data/jobs.json yet. Run python -m commands.pull first.", file=sys.stderr)
        return 1
    try:
        client = Notion(secret("NOTION_TOKEN"))
        database_id = secret("NOTION_DATABASE_ID")
    except MissingSecret as err:
        print(err, file=sys.stderr)
        return 1

    rubric = Rubric.load(args.goal)
    profile = SkillProfile.load(args.profile) if args.profile.exists() else None
    people = contacts.load()

    try:
        if args.dry_run:
            rename, add = missing_columns(client.request("GET", f"databases/{database_id}"))
            changed = ([f"{rename} → Role"] if rename else []) + list(add)
        else:
            changed = ensure_columns(client, database_id)
        if changed:
            print(("Would add" if args.dry_run else "Added") + " columns: " + ", ".join(changed))
        rows = client.pages(database_id)
        existing = {row_key(page): page["id"] for page in rows}
        links = {row_key(page): page["url"] for page in rows if row_key(page)}

        added = updated = 0
        now_skipped = []
        for job in jobs:
            ad = from_record(job)
            result = rubric.score(ad)
            page_id = existing.get(job["key"])
            if not page_id and too_old(job):
                continue
            if result.skipped:
                if page_id:
                    now_skipped.append(f'{job["company"]} — {job["role"]}: {result.knockouts[0][0]}')
                continue
            fit = profile.match(ad) if profile else None
            if page_id:
                if not args.dry_run:
                    client.request("PATCH", f"pages/{page_id}", {"properties": tool_properties(job, result, fit)})
                updated += 1
            else:
                if not args.dry_run:
                    page = create_row(client, database_id, job, result, fit,
                                      people.get(contacts.company_link(job)))
                    links[job["key"]] = page["url"]
                added += 1
                print(f'  + {result.total:>3}  {job["company"]} — {job["role"]}')
    except NotionError as err:
        print(err, file=sys.stderr)
        return 1
    if not args.dry_run:
        save_pages(links)  # for the dashboard's "Track in Notion" buttons

    verb = "Would add" if args.dry_run else "Added"
    print(f"{verb} {added} · {'would refresh' if args.dry_run else 'refreshed'} {updated}")
    if now_skipped:
        print("In Notion but now knocked out by the rubric (left alone, delete them yourself if you agree):")
        for line in now_skipped:
            print("  - " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
