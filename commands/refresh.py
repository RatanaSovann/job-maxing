"""Get the latest: pull new jobs, send them to Notion, rebuild the job list page.

    python -m commands.refresh              the same as the dashboard's "Pull latest jobs" button
    python -m commands.refresh --no-pull    just sync + dashboard (free)
    python -m commands.refresh --add LINK   add a job from a link instead of pulling (free)

Each step runs even if an earlier one fails, so a blocked board never stops
Notion or the dashboard from updating. Output goes to data/logs/refresh-<date>.log.

Budget guard: before pulling, it checks this month's Apify spend and skips the
pull if it could take spend past BUDGET_SHARE of the monthly limit. Research
(commands/research.py) is never part of this: it costs money per company and
needs you to choose the company.
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from typing import Callable

from commands.pull import PROGRESS_MARK
from jobmax.apify import PullError, usage
from jobmax.config import ROOT, MissingSecret, secret
from jobmax.store import DATA

LOGS = DATA / "logs"
BUDGET_SHARE = 0.8     # pulls stop at 80% of the monthly Apify limit
PULL_MAX_COST = 0.14   # the most one pull can cost: both boards' caps (see pull --dry-run)


def _pull_allowed() -> tuple[bool, str]:
    try:
        spent, limit = usage(secret("APIFY_TOKEN"))
    except (MissingSecret, PullError) as err:
        return False, f"could not check Apify spend ({err}), so not pulling"
    if not limit:
        return False, f"Apify reported no monthly limit (spent ${spent}), so not pulling"
    if spent + PULL_MAX_COST > BUDGET_SHARE * limit:
        return False, (f"Apify spend is ${spent:.2f} of ${limit:.0f}; a pull could pass the "
                       f"{BUDGET_SHARE:.0%} guard, so not pulling")
    return True, f"Apify spend ${spent:.2f} of ${limit:.0f}"


def run(say: Callable[[str], None], pull: bool = True, links: list[str] | None = None,
        on_step: Callable[[int, int, str], None] = lambda i, n, name: None,
        on_progress: Callable[[float, str], None] = lambda part, text: None) -> list[str]:
    """Run every step, passing each output line to say() as it happens.

    on_step(i, n, name) is called as step i of n starts. on_progress(part, text) reports
    how far through the current step it is (0-1), for steps that can tell (the pull).
    links: jobs to add from pasted links (commands/add.py) instead of pulling.
    Returns the names of failed steps.
    Everything is also written to today's log.
    """
    LOGS.mkdir(parents=True, exist_ok=True)
    failed = []
    with (LOGS / f"refresh-{datetime.now():%Y-%m-%d}.log").open("a", encoding="utf-8") as log:
        def out(line: str) -> None:
            say(line)
            log.write(line + "\n")
            log.flush()

        out(f"=== {datetime.now():%Y-%m-%d %H:%M} refresh ===")
        steps = [("Sending to Notion", ["commands.sync_notion"]),
                 ("Rebuilding the job list", ["commands.dashboard"])]
        if links:
            out("Pull: skipped (adding from a link)")
            steps.insert(0, ("Adding the job", ["commands.add", *links]))
        elif pull:
            allowed, why = _pull_allowed()
            out(f"Pull: {why}")
            if allowed:
                steps.insert(0, ("Pulling new jobs", ["commands.pull"]))
        else:
            out("Pull: skipped (--no-pull)")

        # Unbuffered + UTF-8, so each line arrives as soon as the step prints it.
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "JOBMAX_PROGRESS": "1"}
        for i, (name, command) in enumerate(steps, 1):
            on_step(i, len(steps), name)
            out(f"--- {name} ---")
            with subprocess.Popen([sys.executable, "-m", *command], cwd=ROOT, env=env, text=True,
                                  encoding="utf-8", errors="replace",
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as step:
                for line in step.stdout:
                    if line.startswith(PROGRESS_MARK):
                        part, _, text = line[len(PROGRESS_MARK):].strip().partition(" ")
                        try:
                            on_progress(float(part), text)
                        except ValueError:
                            pass
                    elif line.strip():
                        out("  " + line.rstrip())
            # pull exits 2 when every board failed: worth flagging, not fatal.
            if step.returncode != 0:
                failed.append(name)
                out(f"{name} failed (exit {step.returncode}); carrying on.")

        out(f"=== finished {datetime.now():%H:%M}"
            + (f" · failed: {', '.join(failed)}" if failed else " · all steps ok") + " ===\n")
    return failed


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-pull", action="store_true", help="skip the paid pull, just sync + dashboard")
    parser.add_argument("--add", nargs="+", default=[], metavar="LINK",
                        help="add these job links instead of pulling (free)")
    args = parser.parse_args()
    return 1 if run(print, pull=not args.no_pull, links=args.add) else 0


if __name__ == "__main__":
    raise SystemExit(main())
