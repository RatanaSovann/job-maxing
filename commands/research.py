"""Research companies you're pursuing and write a brief into each job's Notion page.

    python -m commands.research --dry-run               which jobs it would research, and roughly what it costs
    python -m commands.research                          every job whose Status is "Researching" in Notion
    python -m commands.research --company Praemium       just these companies, whatever their status
    python -m commands.research --company ELMO --refresh write a new brief even if one exists
    python -m commands.research --ad my_job.txt          a job that isn't in your list yet (see below)

--ad takes an ad saved by hand in the fixtures/README.md format (company: / role: header,
a --- line, then the whole ad). The job is added to your list and to Notion like any
other (board "manual", Status "Researching"), then researched. Optional header lines
`linkedin:` (the company's LinkedIn page) and `website:` improve contacts and research.

Uses ANTHROPIC_API_KEY (Claude + web search). Each brief is added to the bottom of
the job's Notion page and the "Research brief" column gets today's date, so a job
is not researched twice unless you ask with --refresh. Nothing is ever deleted.

Each brief names the people to send the artifact to (how many and which kinds come
from `contacts:` in the goal file): your LinkedIn connections there first, then
people found on the web, each with a source. If the job's Contacts column is empty,
they are written there too; if you've already filled it in, it is left alone.

Before each brief the ad is checked (free). A closed ad is skipped, so you don't pay
for research on a filled role, unless you named the company with --company.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

import anthropic
import yaml

from jobmax import connections, contacts, notion as tracker, store
from jobmax.ads import AdFormatError, from_record, load_ad
from jobmax.config import MissingSecret, secret
from jobmax.notion import (BRIEF, TEXT_LIMIT, Notion, NotionError, append_blocks, create_row, ensure_columns,
                           markdown_blocks, row_key)
from jobmax.links import CLOSED, still_open
from jobmax.research import MODEL, build_prompt, people_from, research
from jobmax.scorer import Rubric
from jobmax.skills import SkillProfile
from jobmax.sources import from_ad

from jobmax.config import ROOT
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
ESTIMATE = "$0.60–0.90"  # per company; 6 searches cost $0.52–0.66, finding people adds up to 2 more


def _plain(prop: dict) -> str:
    kind = prop.get("type")
    if kind in ("rich_text", "title"):
        return "".join(t["plain_text"] for t in prop[kind])
    if kind == "select":
        return (prop["select"] or {}).get("name", "")
    if kind == "date":
        return (prop["date"] or {}).get("start", "")
    return ""


def _add_outside_job(path: Path, rows: list[dict], ctx: dict, dry_run: bool) -> dict | None:
    """Put a hand-saved ad into the job list and Notion. Returns its Notion row (None on a dry run)."""
    record = from_ad(load_ad(path))
    jobs = store.load()
    same = next((j for j in jobs if j["key"] == record["key"] or j["dedupe_key"] == record["dedupe_key"]), None)
    job = same or record
    if same:
        print(f'Already in your list (from {same["source"]}): {same["company"]} — {same["role"]}')
    result = ctx["rubric"].score(from_record(job))
    fit = ctx["profile"].match(from_record(job)) if ctx["profile"] else None
    if result.skipped:
        print(f"Note: the rules would skip this job ({result.knockouts[0][0]}). Researching anyway, "
              "since you asked for it.")
    else:
        skills = f", skills {fit.score}" if fit and fit.score is not None else ""
        print(f'Scored: PR {result.total}{skills} · {result.likely_code}')

    page = next((p for p in rows if row_key(p) == job["key"]), None)
    if dry_run:
        if not same:
            print("Would add it to your job list.")
        if page is None:
            print('Would add it to Notion with Status "Researching".')
        return page
    if not same:
        store.merge([record])
        print("Added to your job list (board: manual).")
    if page is None:
        page = create_row(ctx["notion"], ctx["database_id"], job, result, fit,
                          contacts.load().get(contacts.company_link(job)), status="Researching")
        pages = tracker.load_pages()
        pages[job["key"]] = page["url"]
        tracker.save_pages(pages)  # so the dashboard's "Track in Notion" button works at once
        print(f"Added to Notion: {page['url']}")
    return page


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company", nargs="+", help="only companies whose name contains one of these")
    parser.add_argument("--ad", type=Path, help="a job ad saved as a text file, for a job not in your list")
    parser.add_argument("--refresh", action="store_true", help="write a new brief even if one exists")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen, spend nothing")
    parser.add_argument("--goal", type=Path, default=ROOT / "goals" / "pr_australia.yaml")
    parser.add_argument("--profile", type=Path, default=ROOT / "profile" / "skills.yaml")
    args = parser.parse_args()

    try:
        notion = Notion(secret("NOTION_TOKEN"))
        database_id = secret("NOTION_DATABASE_ID")
        api_key = "" if args.dry_run else secret("ANTHROPIC_API_KEY")
    except MissingSecret as err:
        print(err, file=sys.stderr)
        return 1

    rubric = Rubric.load(args.goal)
    profile = SkillProfile.load(args.profile) if args.profile.exists() else None
    config = yaml.safe_load(args.goal.read_text(encoding="utf-8-sig"))
    rules = (config.get("outreach") or {}).get("rules", [])
    wanted = config.get("contacts") or {}
    ctx = {"notion": notion, "database_id": database_id, "rubric": rubric, "profile": profile}

    try:
        if not args.dry_run:
            ensure_columns(notion, database_id)
        rows = notion.pages(database_id)
        if args.ad:
            page = _add_outside_job(args.ad, rows, ctx, args.dry_run)
            rows = [page] if page else []
    except AdFormatError as err:
        print(f"Bad ad file — {err}", file=sys.stderr)
        return 1
    except NotionError as err:
        print(err, file=sys.stderr)
        return 1

    if args.ad and args.dry_run and not rows:
        print(f"Would then research it with {MODEL} + web search, roughly {ESTIMATE}.\n\n"
              "Dry run — nothing added, nothing researched, nothing charged.")
        return 0

    todo, done_before = [], []
    for page in rows:
        props = page["properties"]
        company, status = _plain(props.get("Company", {})), _plain(props.get("Status", {}))
        if args.company:
            if not any(c.lower() in company.lower() for c in args.company):
                continue
        elif status != "Researching" and not args.ad:
            continue
        if _plain(props.get(BRIEF, {})) and not args.refresh:
            done_before.append(company)
            continue
        todo.append(page)

    if done_before:
        print("Already have a brief (use --refresh for a new one): " + ", ".join(done_before))
    if not todo:
        if not done_before:
            print('Nothing to research. Set a job\'s Status to "Researching" in Notion, or use --company / --ad.')
        return 0

    print(f"{len(todo)} to research with {MODEL} + web search, roughly {ESTIMATE} each:")
    for page in todo:
        props = page["properties"]
        print(f'  {_plain(props.get("Company", {}))} — {_plain(props.get("Role", {}))}')
    if args.dry_run:
        print("\nDry run — nothing researched, nothing charged.")
        return 0

    stored = store.load()
    jobs = {job["key"]: job for job in stored}
    try:
        known = connections.index(connections.load())
    except ValueError as err:
        print(f"Skipping your LinkedIn connections: {err}")
        known = {}
    client = anthropic.Anthropic(api_key=api_key)
    total = 0.0
    for page in todo:
        props = page["properties"]
        company = _plain(props.get("Company", {}))
        job = jobs.get(row_key(page))
        if job is None:
            print(f"\n{company}: this job is no longer in data/jobs.json, skipped.")
            continue
        state, why = still_open(job)
        job["ad_status"] = {"state": state, "why": why, "checked": date.today().isoformat()}
        store.save(stored)
        if state == CLOSED:
            if not args.company:
                print(f"\n{company}: the ad has closed ({why}), so not researched. "
                      f"Research it anyway with --company \"{company}\".")
                continue
            print(f"\n{company}: note, the ad has closed ({why}). Researching anyway, since you named it.")
        print(f"\n{company}: researching…", flush=True)
        prompt = build_prompt(job, rubric.score(from_record(job)), profile,
                              _plain(props.get("Contacts", {})), rules,
                              connections.as_text(connections.known_at(job["company"], known)),
                              wanted.get("mix", []), wanted.get("exclude_titles", []))
        try:
            brief = research(client, prompt)
        except (RuntimeError, anthropic.APIError) as err:
            print(f"  failed, nothing written: {err}")
            continue

        heading = {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [
            {"text": {"content": f"Research brief · {date.today():%d %b %Y}"}}]}}
        note = {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
            {"text": {"content": f"Written by {brief.model} from web sources. Check the links before relying on it."},
             "annotations": {"italic": True, "color": "gray"}}]}}
        update = {BRIEF: {"date": {"start": date.today().isoformat()}}}
        people = people_from(brief.markdown)
        if people and not _plain(props.get("Contacts", {})).strip():  # never overwrite your own list
            update["Contacts"] = {"rich_text": [{"text": {"content": people[:TEXT_LIMIT]}}]}
        try:
            append_blocks(notion, page["id"], [heading, note] + markdown_blocks(brief.markdown))
            notion.request("PATCH", f"pages/{page['id']}", {"properties": update})
        except NotionError as err:
            print(f"  researched but could not write to Notion: {err}")
            continue
        total += brief.cost_usd
        print(f"  written to Notion · {brief.searches} searches, {brief.results} pages found · "
              f"about ${brief.cost_usd:.2f}")
        if people:
            print("  People to send it to" + (" (also saved to Contacts):" if "Contacts" in update else ":"))
            for line in people.splitlines():
                print(f"    - {line}")

    print(f"\nDone. About ${total:.2f} in total (an upper estimate: cached reads are counted at full price).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
