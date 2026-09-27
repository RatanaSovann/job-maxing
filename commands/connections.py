"""Who you already know at the companies in your job list.

    python -m commands.connections

Reads data/Connections.csv, your own LinkedIn connections export:
LinkedIn → Settings → Data privacy → Get a copy of your data → pick "Connections"
→ LinkedIn emails a download link (usually within minutes) → unzip → save
Connections.csv in the data/ folder. Download a fresh copy now and then.

Free and offline. The job list page and research briefs pick these people up by
themselves; this command just lists them.
"""

import argparse
import sys

from jobmax import connections, store
from jobmax.sources import too_old

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args(argv)

    try:
        people = connections.load()
    except ValueError as err:
        print(err, file=sys.stderr)
        return 1
    if not people:
        print(f"No connections file at {connections.CONNECTIONS}.\n\n" + __doc__.split("\n\n")[2])
        return 1

    by_company = connections.index(people)
    roles: dict[str, list[str]] = {}
    for job in store.load():
        if not too_old(job):
            roles.setdefault(job["company"], []).append(job["role"])

    hits = {company: known for company in roles if (known := connections.known_at(company, by_company))}
    print(f"{len(people)} connections · {len(roles)} companies in your job list · "
          f"you know someone at {len(hits)}\n")
    for company, known in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        print(f"{company}  ({'; '.join(roles[company])})")
        for p in known:
            typed = f"  [LinkedIn says: {p['company']}]" if p["company"] != company else ""
            print(f"  - {p['name']} · {p['position'] or 'position not listed'}{typed}")
            if p["linkedin"]:
                print(f"    {p['linkedin']}")
        print()
    if not hits:
        print("No overlap yet. It's worth re-checking after each pull.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
