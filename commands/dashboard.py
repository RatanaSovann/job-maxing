"""Score every stored job and write the job list page.

    python -m commands.dashboard              data/jobs.json + data/contacts.json -> out/dashboard.html
    python -m commands.dashboard --open       ...and open it in the browser

Free: nothing here touches the network. Re-run it after any pull, contact
lookup or rubric change.
"""

import argparse
import os
import sys
from pathlib import Path

from jobmax import connections, contacts, notion, store
from jobmax.ads import from_record
from jobmax.render import render_dashboard
from jobmax.scorer import Rubric
from jobmax.skills import SkillProfile
from jobmax.sources import MAX_AGE_DAYS, closed, too_old

from jobmax.config import ROOT
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--goal", type=Path, default=ROOT / "goals" / "pr_australia.yaml")
    parser.add_argument("--profile", type=Path, default=ROOT / "profile" / "skills.yaml",
                        help="skills profile for the Skills fit score (skipped if missing)")
    parser.add_argument("--out", type=Path, default=ROOT / "out" / "dashboard.html")
    parser.add_argument("--open", action="store_true", help="open the page when done")
    args = parser.parse_args(argv)

    jobs = store.load()
    if not jobs:
        print("No jobs in data/jobs.json yet. Run python -m commands.pull first.", file=sys.stderr)
        return 1

    rubric = Rubric.load(args.goal)
    people = contacts.load()
    try:
        known = connections.index(connections.load())
    except ValueError as err:  # a wrong file shouldn't stop the page being built
        print(f"Skipping your LinkedIn connections: {err}")
        known = {}
    profile = SkillProfile.load(args.profile) if args.profile.exists() else None
    if profile is None:
        print(f"No skills profile at {args.profile}, so no Skills fit score.")
    rows, old, gone = [], 0, 0
    for job in jobs:
        if too_old(job):  # still in data/jobs.json (and Notion, if it was sent), just not listed
            old += 1
            continue
        if closed(job):  # the ad has closed (commands/check_open.py)
            gone += 1
            continue
        ad = from_record(job)
        rows.append((job, rubric.score(ad), people.get(contacts.company_link(job)), contacts.is_agency(job),
                     profile.match(ad) if profile else None, connections.known_at(job["company"], known)))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    html = render_dashboard(rows, rubric.name, notion.database_url(), notion.load_pages(),
                            rubric.config.get("contacts", {}).get("mix", []))
    args.out.write_text(html, encoding="utf-8")

    skipped = sum(1 for r in rows if r[1].skipped)
    with_people = sum(1 for r in rows if r[2] and r[2].get("people"))
    print(f"{len(rows)} jobs · {len(rows) - skipped} scored · {skipped} skipped · "
          f"{with_people} with contacts · {old} hidden (posted over {MAX_AGE_DAYS} days ago) · "
          f"{gone} hidden (ad closed) → {args.out}")
    if args.open:
        os.startfile(args.out)  # Windows: opens in the default browser
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
