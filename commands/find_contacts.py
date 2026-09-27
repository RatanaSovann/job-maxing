"""Find 3 people to connect with at each company in data/jobs.json.

    python -m commands.find_contacts --dry-run          what it would cost, spend nothing
    python -m commands.find_contacts                    names + LinkedIn profiles
    python -m commands.find_contacts --email            also search for email (3x the price)
    python -m commands.find_contacts --company ELMO     just these companies
    python -m commands.find_contacts --min-score 40     only companies with a job scoring 40+

Cached in data/contacts.json — a company already looked up is never paid for
twice. Use --refresh to look one up again.
"""

import argparse
import sys
from pathlib import Path

import yaml

from jobmax import contacts, store
from jobmax.ads import from_record
from jobmax.apify import PullError, usage
from jobmax.config import MissingSecret, secret
from jobmax.scorer import Rubric

from jobmax.config import ROOT
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--goal", type=Path, default=ROOT / "goals" / "pr_australia.yaml")
    parser.add_argument("--email", action="store_true", help="also search for email addresses")
    parser.add_argument("--company", nargs="+", help="only companies whose name contains one of these")
    parser.add_argument("--min-score", type=float, default=None,
                        help="only companies with at least one job scoring this high")
    parser.add_argument("--include-agencies", action="store_true",
                        help="also look up recruitment agencies (skipped by default — they "
                             "advertise other companies' jobs and returned nobody useful)")
    parser.add_argument("--refresh", action="store_true", help="re-fetch companies already cached")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = yaml.safe_load(args.goal.read_text(encoding="utf-8-sig"))
    mix = config.get("contacts", {}).get("mix", [])
    exclude = config.get("contacts", {}).get("exclude_titles", [])
    if not mix:
        print(f"No 'contacts:' section in {args.goal.name}", file=sys.stderr)
        return 1

    jobs = store.load()
    if not jobs:
        print("No jobs in data/jobs.json — run pull.py first.", file=sys.stderr)
        return 1

    if args.min_score is not None:
        rubric = Rubric.load(args.goal)
        keep = {j["key"] for j in jobs
                if (r := rubric.score(from_record(j))) and not r.skipped and r.total >= args.min_score}
        jobs = [j for j in jobs if j["key"] in keep]

    companies = contacts.companies_from_jobs(jobs)
    cache = contacts.load()

    wanted = []
    for url, company in companies.items():
        if args.company and not any(c.lower() in company["company"].lower() for c in args.company):
            continue
        if company["is_agency"] and not args.include_agencies:
            continue
        if url in cache and not args.refresh:
            continue
        wanted.append(company)

    mode = "email" if args.email else "profile"
    cost = contacts.estimate(len(wanted), mix, mode)
    per_company = sum(int(g.get("wanted", 1)) for g in mix)

    print(f"Companies in store   {len(companies)}")
    print(f"Already cached       {sum(1 for u in companies if u in cache)}")
    print(f"To look up           {len(wanted)}")
    breakdown = ", ".join(f"{g['wanted']} {g['role']}" for g in mix)
    print(f"Wanted per company   {per_company} ({breakdown})")
    print(f"Mode                 {mode} (${contacts.MODES[mode][1]}/person)")
    print(f"Cost                 up to ${cost:.3f}")

    if not wanted:
        print("\nNothing to look up.")
        return 0
    if args.dry_run:
        print("\n" + "\n".join(f"  {c['company']}{'  [agency]' if c['is_agency'] else ''}" for c in wanted))
        print("\nDry run — nothing fetched, nothing charged.")
        return 0

    try:
        token = secret("APIFY_TOKEN")
    except MissingSecret as err:
        print(f"\n{err}", file=sys.stderr)
        return 1

    print("\nLooking up… (one run per role group)")
    found, spent = contacts.fetch_for_companies(
        wanted, mix, token, mode=mode, exclude=exclude,
        on_status=lambda s: print(f"  {s.lower()}"))

    failed = [c for c in wanted if c["linkedin"] not in found]
    wanted = [c for c in wanted if c["linkedin"] in found]
    for company in wanted:
        cache[company["linkedin"]] = contacts.record(company, found[company["linkedin"]], mode)
    contacts.save(cache)
    if failed:
        print("\nLookup failed, kept what was cached before: " + ", ".join(c["company"] for c in failed))

    try:
        used, limit = usage(token)
        print(f"\nApify credit used this cycle: ${used} of ${limit}\n")
    except PullError:
        print(f"\nRun reported ${spent:.4f}\n")

    short = []
    for company in wanted:
        people = cache[company["linkedin"]]["people"]
        tag = "  [agency]" if company["is_agency"] else ""
        print(f"{company['company']}{tag} — {len(people)}/{per_company}")
        for p in people:
            email = f"  <{p['email']}>" if p.get("email") else ""
            print(f"   {p['targeted_as']:<8} {p['name'][:26]:<26} {p['title'][:46]:<46}{email}")
            print(f"            {p['linkedin']}")
        if len(people) < per_company:
            short.append(company["company"])
        print()

    if short:
        print(f"Fewer than {per_company} found at: {', '.join(short)}")
        print("Usually means nobody at that company holds those titles, or they are outside Sydney.")
    print(f"{len(cache)} companies in data/contacts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
