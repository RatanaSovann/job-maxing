"""Check which job ads have closed.

    python -m commands.check_open              ads not checked yet today
    python -m commands.check_open --all        every ad on the job list, closed ones too
    python -m commands.check_open --company ELMO

Free: it re-reads each ad page (Seek, LinkedIn, or the careers site). Also runs as
a step of the "Pull latest jobs" button. A job is only marked closed on a clear sign
(the board says so, the ad is gone, or its closing date has passed); anything
unclear is "unknown" and the job stays listed.

Closed jobs drop off the job list page and aren't added to Notion. Rows already in
Notion get the date in their "Ad closed" column. Nothing is deleted: re-run with
--all and a job that turns out to be open again comes back. A job you removed
yourself (the Remove button on the job list) is never re-checked.
"""

import argparse
import sys
import time
from datetime import date

from commands.pull import progress
from jobmax import store
from jobmax.links import CLOSED, OPEN, still_open
from jobmax.sources import too_old

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PAUSE = 0.5        # seconds between pages, to stay polite to the boards


def due(job: dict, everything: bool) -> bool:
    status = job.get("ad_status") or {}
    if status.get("by_you"):  # you removed it on the job list; your call stands
        return False
    if everything:
        return True
    if status.get("state") == CLOSED:
        return False
    # Ads close any day, so an open one is re-read once a day (a second pull that day skips it).
    return status.get("state") != OPEN or status.get("checked", "") < date.today().isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="re-check every ad, including closed ones")
    parser.add_argument("--company", nargs="+", help="only companies whose name contains one of these")
    args = parser.parse_args(argv)

    jobs = store.load()
    todo = [j for j in jobs if not too_old(j) and due(j, args.all or bool(args.company))
            and (not args.company or any(c.lower() in j["company"].lower() for c in args.company))]
    if not todo:
        print("Every ad on the job list was already checked today. Nothing to do.")
        return 0

    print(f"Checking {len(todo)} ads…")
    counts = {"open": 0, "closed": 0, "unknown": 0}
    newly_closed, reopened = [], []
    try:
        for i, job in enumerate(todo):
            progress(i / len(todo), f"{i} of {len(todo)} ads checked")
            was = (job.get("ad_status") or {}).get("state")
            state, why = still_open(job)
            job["ad_status"] = {"state": state, "why": why, "checked": date.today().isoformat()}
            counts[state] += 1
            if state == CLOSED and was != CLOSED:
                newly_closed.append((job, why))
            elif state == OPEN and was == CLOSED:
                reopened.append(job)
            time.sleep(PAUSE)
    finally:  # Ctrl+C part-way still keeps what was checked
        store.save(jobs)

    print(f"Open {counts['open']} · closed {counts['closed']} · couldn't tell {counts['unknown']}")
    if newly_closed:
        print("\nClosed since the last check (hidden from the job list now):")
        for job, why in newly_closed:
            print(f"  {job['company'][:34]:<34} {job['role'][:44]:<44} [{why}]")
    if reopened:
        print("\nOpen again (back on the job list):")
        for job in reopened:
            print(f"  {job['company'][:34]:<34} {job['role'][:44]}")
    if counts["unknown"]:
        print("\n\"Couldn't tell\" jobs stay listed; they're checked again next time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
