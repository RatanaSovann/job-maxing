"""Score every ad in a folder against a goal rubric and write an HTML page.

    python -m commands.score                      # fixtures/ -> out/jobs.html
    python -m commands.score --ads fixtures --goal goals/pr_australia.yaml
"""

import argparse
import sys
from pathlib import Path

from jobmax.ads import AdFormatError, load_dir
from jobmax.render import render
from jobmax.scorer import Rubric

from jobmax.config import ROOT

# Windows consoles default to cp1252, which cannot print "—" or "→".
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ads", type=Path, default=ROOT / "fixtures")
    parser.add_argument("--goal", type=Path, default=ROOT / "goals" / "pr_australia.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "out" / "jobs.html")
    args = parser.parse_args()

    if not args.ads.is_dir():
        print(f"No ads folder at {args.ads}", file=sys.stderr)
        return 1

    try:
        ads = load_dir(args.ads)
    except AdFormatError as err:
        print(f"Bad ad file — {err}", file=sys.stderr)
        return 1
    if not ads:
        print(f"No .txt ad files in {args.ads} — see fixtures/README.md", file=sys.stderr)
        return 1

    rubric = Rubric.load(args.goal)
    results = [rubric.score(ad) for ad in ads]

    width = max(len(r.ad.title) for r in results)
    for r in sorted(results, key=lambda r: (r.skipped, -r.total)):
        if r.skipped:
            print(f"{r.ad.title:<{width}}   0  KNOCKOUT: {r.knockouts[0][0]}")
        else:
            breakdown = " ".join(
                f"{c.name.split()[0].lower()} {c.points:g}{'?' if c.unknown else ''}"
                for c in r.components
            )
            print(f"{r.ad.title:<{width}} {r.total:>3}  {breakdown}  [{r.likely_code}]")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(results, rubric.name), encoding="utf-8")
    print(f"\n{len(results)} ads → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
