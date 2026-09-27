"""Pull jobs from the boards into data/jobs.json.

    python -m commands.pull                                  primary keywords, LinkedIn + Seek, 20 jobs each
    python -m commands.pull --source seek                    one board only
    python -m commands.pull --group core --rows 30
    python -m commands.pull --titles "Payroll Analyst" "Tax Analyst"
    python -m commands.pull --dry-run                        show the plan and the cost, spend nothing
    python -m commands.pull --from-raw data/raw/<file>.json  re-read a saved pull, free

Costs real money on the Apify free plan ($5/month), so it always prints the
estimate first and caps each run at Apify's end.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from jobmax import store
from jobmax.apify import PullError, account, run_actor
from jobmax.config import MissingSecret, secret
from jobmax.sources import SOURCES, Search, too_senior

from jobmax.config import ROOT
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# refresh.py sets JOBMAX_PROGRESS and turns lines starting with PROGRESS_MARK into the
# page's progress bar: "@progress <fraction 0-1> <what's happening>". Off for manual runs.
PROGRESS_MARK = "@progress "


def progress(fraction: float, text: str) -> None:
    if os.environ.get("JOBMAX_PROGRESS"):
        print(f"{PROGRESS_MARK}{min(max(fraction, 0.0), 1.0):.3f} {text}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default="all", choices=["all", *sorted(SOURCES)])
    parser.add_argument("--goal", type=Path, default=ROOT / "goals" / "pr_australia.yaml")
    parser.add_argument("--group", default="primary",
                        help="which search_keywords group from the goal file (default: primary)")
    parser.add_argument("--titles", nargs="+", help="search these titles instead of a group")
    parser.add_argument("--location", help="override the goal file's search.location")
    parser.add_argument("--rows", type=int, default=20, help="jobs to ask each board for (default: 20)")
    parser.add_argument("--max-cost", type=float, default=None,
                        help="hard USD cap per board (default: estimate + 50%%)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from-raw", type=Path,
                        help="re-read a saved data/raw/*.json file instead of pulling (free)")
    args = parser.parse_args()

    config = yaml.safe_load(args.goal.read_text(encoding="utf-8-sig"))
    filters = config.get("search", {})
    exclude = filters.get("exclude_title_words", [])

    if args.from_raw:
        # Raw files are named <source>-<timestamp>.json by store.save_raw.
        source = SOURCES.get(args.from_raw.name.split("-")[0])
        if not source:
            print(f"Can't tell which board {args.from_raw.name} came from.", file=sys.stderr)
            return 1
        items = json.loads(args.from_raw.read_text(encoding="utf-8-sig"))
        return report_on({source.name: (items, None)}, exclude, args.from_raw, token=None)

    groups = config.get("search_keywords", {})
    if args.titles:
        titles = args.titles
    elif args.group in groups:
        titles = groups[args.group]
    else:
        print(f"No keyword group '{args.group}' in {args.goal.name}. "
              f"Available: {', '.join(groups)}", file=sys.stderr)
        return 1

    search = Search(
        titles=titles,
        location=args.location or filters.get("location", "Australia"),
        rows=args.rows,
        experience_levels=filters.get("experience_levels", []),
        exclude_title_words=exclude,
    )
    sources = list(SOURCES.values()) if args.source == "all" else [SOURCES[args.source]]

    print(f"Titles    {', '.join(titles)}")
    print(f"Location  {search.location}")
    print(f"Levels    {', '.join(search.experience_levels) or 'any'}")
    print(f"Excluding titles with: {', '.join(exclude) or 'nothing'}")
    print(f"Asking    {args.rows} jobs per board, posted in the last 30 days\n")

    plans = []
    for source in sources:
        try:
            request = source.build_input(search)
        except ValueError as err:
            print(f"Bad search filter in {args.goal.name} — {err}", file=sys.stderr)
            return 1
        estimate = source.price_per_run_usd + args.rows * source.price_per_item_usd
        # Apify rejects any run capped under $0.05.
        cap = args.max_cost if args.max_cost is not None else max(0.05, round(estimate * 1.5 + 0.01, 4))
        plans.append((source, request, cap))
        print(f"  {source.name:<9} {source.actor:<32} ~${estimate:.3f} · capped at ${cap:.4f}")

    if args.dry_run:
        print("\nDry run — nothing pulled, nothing charged.")
        return 0

    try:
        token = secret("APIFY_TOKEN")
    except MissingSecret as err:
        print(f"\n{err}", file=sys.stderr)
        return 1

    pulled, failed = {}, []
    for i, (source, request, cap) in enumerate(plans):
        print(f"\nRunning {source.name}… (a minute or two)")
        # Each board gets an equal slice of the bar, filled as its jobs arrive.
        progress(i / len(plans), f"{source.name}: starting")
        try:
            items, cost = run_actor(
                source.actor,
                request,
                token,
                max_items=args.rows,
                max_cost_usd=cap,
                on_status=lambda s: print(f"  {s.lower()}"),
                on_items=lambda n, i=i, name=source.name: progress(
                    (i + min(n, args.rows) / args.rows) / len(plans),
                    f"{name}: {n} of {args.rows} jobs"),
            )
        except PullError as err:
            # Expected failure mode: a board blocks, the actor breaks, the
            # network drops. The other board still runs; the store is untouched
            # for this one, so tomorrow's pull just carries on.
            print(f"  {source.name} failed — {err}", file=sys.stderr)
            failed.append(source.name)
            continue
        store.save_raw(source.name, items)
        pulled[source.name] = (items, cost)

    if not pulled:
        print("\nNothing was written. data/jobs.json is unchanged.", file=sys.stderr)
        return 2
    code = report_on(pulled, exclude, None, token)
    if failed:
        print(f"\nFailed this time: {', '.join(failed)}. Everything else was saved.")
    return code


def report_on(pulled: dict, exclude: list[str], raw_path, token) -> int:
    records, unusable, dropped = [], 0, []
    for name, (items, cost) in pulled.items():
        source = SOURCES[name]
        for item in items:
            record = source.to_record(item)
            if not record:
                unusable += 1
            elif word := too_senior(record["role"], exclude):
                dropped.append((record, word))
            else:
                records.append(record)
        if cost is not None:
            print(f"\n{name}: {len(items)} pulled, cost ${cost:.4f}")

    report = store.merge(records, unusable=unusable)

    print(f"\nKept {len(records)} · new {len(report.added)} · "
          f"already had {len(report.seen_before)} · "
          f"duplicate titles {len(report.duplicates_in_pull)} · "
          f"senior (dropped) {len(dropped)} · unusable {unusable}")
    if raw_path:
        print(f"Re-read from {raw_path}")

    if dropped:
        print("\nDropped as senior (still in data/raw/):")
        for r, word in dropped:
            print(f"  {r['source']:<8} {r['company'][:30]:<30}  {r['role'][:50]}  [\"{word}\"]")

    if report.added:
        print("\nNew jobs:")
        width = min(34, max(len(r["company"]) for r in report.added))
        for r in report.added:
            recruiter = (r["recruiter"]["name"] or "").strip()
            print(f"  {r['source']:<8} {r['company'][:width]:<{width}}  {r['role'][:44]:<44} "
                  f"{r['posted'] or '?':<10} {('· ' + recruiter) if recruiter else ''}")

    everything = store.load()
    if everything:
        print(f"\nField coverage across all {len(everything)} stored jobs:")
        for name, got, total in store.coverage(everything):
            bar = "#" * round(12 * got / total) if total else ""
            print(f"  {name:<18} {got:>3}/{total:<3} {bar}")

    try:
        plan = account(token) if token else {}
        limit = (plan.get("plan") or {}).get("maxMonthlyUsageUsd")
        if limit:
            print(f"\nMonthly Apify credit: ${limit} on the {(plan.get('plan') or {}).get('id')} plan.")
    except PullError:
        pass

    print(f"\n{len(everything)} jobs in data/jobs.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
