"""The Notion job tracker: a thin API client and the tracker's columns.

Two kinds of column, and the split is the whole point:
  - TOOL_COLUMNS are rewritten on every sync (scores, reasons, job details).
  - YOUR_COLUMNS are set once when a job is added, then never touched again,
    so a re-sync can't wipe out what you've tracked (status, dates, notes).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from .ads import job_fact
from .config import MissingSecret, secret
from .scorer import Result
from .skills import SkillFit
from .store import DATA

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"
TEXT_LIMIT = 2000  # Notion's cap on one piece of text
PAGES = DATA / "notion_pages.json"  # job key -> its Notion page, written by each sync

TITLE = "Role"
KEY = "Job key"  # the store's job key; how a row is matched on the next sync
BRIEF = "Research brief"

TOOL_COLUMNS = {
    "Company": {"rich_text": {}},
    "PR score": {"number": {}},
    "Skills fit": {"number": {}},
    "Likely code": {"rich_text": {}},
    "Why it scores": {"rich_text": {}},
    "Skills have": {"rich_text": {}},
    "Skills missing": {"rich_text": {}},
    "Salary": {"rich_text": {}},
    "Board": {"select": {}},
    "Job ad": {"url": {}},
    KEY: {"rich_text": {}},
    # Set by research.py when it writes a brief; sync never touches it.
    BRIEF: {"date": {}},
}

STATUSES = ["To review", "Researching", "Applied", "Followed up", "Interview", "Rejected", "Not pursuing"]
ARTIFACT = ["Not started", "Idea", "Drafting", "Sent"]

YOUR_COLUMNS = {
    "Status": {"select": {"options": [{"name": s} for s in STATUSES]}},
    "Date applied": {"date": {}},
    "Follow-up date": {"formula": {"expression": 'dateAdd(prop("Date applied"), 5, "days")'}},
    "Outreach count": {"number": {}},
    "Research done": {"checkbox": {}},
    "Artifact status": {"select": {"options": [{"name": s} for s in ARTIFACT]}},
    "Contacts": {"rich_text": {}},
}


class NotionError(RuntimeError):
    pass


class Notion:
    def __init__(self, token: str):
        self.token = token

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(4):
            req = urllib.request.Request(f"{API}/{path}", data=data, method=method, headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": VERSION,
                "Content-Type": "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    return json.load(response)
            except urllib.error.HTTPError as err:
                if err.code == 429 and attempt < 3:  # rate limited: wait as told, retry
                    time.sleep(float(err.headers.get("Retry-After", 1)))
                    continue
                detail = err.read()[:400].decode("utf-8", "replace")
                raise NotionError(f"Notion returned {err.code} for {method} {path}: {detail}") from err
            except (urllib.error.URLError, TimeoutError) as err:
                raise NotionError(f"Could not reach Notion: {err}") from err
        raise AssertionError("unreachable")

    def pages(self, database_id: str) -> list[dict]:
        rows, cursor = [], None
        while True:
            body = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
            page = self.request("POST", f"databases/{database_id}/query", body)
            rows += page["results"]
            if not page.get("has_more"):
                return rows
            cursor = page["next_cursor"]


def missing_columns(database: dict) -> tuple[str | None, dict]:
    """(current title column name if it needs renaming, columns to add).

    Columns that already exist are left as they are, so options or formulas
    you've changed in Notion survive.
    """
    props = database["properties"]
    title = next(name for name, p in props.items() if p["type"] == "title")
    add = {name: spec for name, spec in {**TOOL_COLUMNS, **YOUR_COLUMNS}.items() if name not in props}
    return (title if title != TITLE else None), add


def ensure_columns(client: Notion, database_id: str) -> list[str]:
    rename, add = missing_columns(client.request("GET", f"databases/{database_id}"))
    changes = dict(add)
    if rename:
        changes[rename] = {"name": TITLE}
    if changes:
        client.request("PATCH", f"databases/{database_id}", {"properties": changes})
    return ([f"{rename} → {TITLE}"] if rename else []) + list(add)


def database_url() -> str:
    """The tracker's web address, or "" if no database is configured."""
    try:
        return "https://www.notion.so/" + secret("NOTION_DATABASE_ID").replace("-", "")
    except MissingSecret:
        return ""


def load_pages(path=PAGES) -> dict[str, str]:
    """Job key -> Notion page URL, as of the last sync. Lets the dashboard link without the network."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_pages(pages: dict[str, str], path=PAGES) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(pages, indent=1, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def row_key(page: dict) -> str:
    prop = page["properties"].get(KEY) or {}
    return "".join(t["plain_text"] for t in prop.get("rich_text", []))


# --------------------------------------------------------------------------
# a job -> a row
# --------------------------------------------------------------------------

def _text(value: str) -> dict:
    value = value[:TEXT_LIMIT]
    return {"rich_text": [{"text": {"content": value}}] if value else []}


def _why(result: Result) -> str:
    lines = [f"+ {h}" for h in result.helps] + [f"− {h}" for h in result.hurts]
    if result.unknowns:
        lines.append("? " + ", ".join(dict.fromkeys(result.unknowns)))
    lines += [f"⚠ {f}" for f in result.flags]
    return "\n".join(lines)


def tool_properties(job: dict, result: Result, fit: SkillFit | None) -> dict:
    """The columns a sync owns. Safe to rewrite every time."""
    code = result.likely_code + (f" · {result.confidence} confidence" if result.confidence else "")
    return {
        TITLE: {"title": [{"text": {"content": job["role"][:TEXT_LIMIT]}}]},
        "Company": _text(job["company"]),
        "PR score": {"number": result.total},
        "Skills fit": {"number": fit.score if fit else None},
        "Likely code": _text(code),
        "Why it scores": _text(_why(result)),
        "Skills have": _text("\n".join([str(h) for h in fit.have] + [f"(partly) {p}" for p in fit.partial])
                             if fit else ""),
        "Skills missing": _text("\n".join(str(m) for m in fit.missing) if fit else ""),
        "Salary": _text(job_fact(job["description"], "Salary") or "?"),
        "Board": {"select": {"name": job["source"]}},
        "Job ad": {"url": job.get("url") or None},
        KEY: _text(job["key"]),
    }


def starting_properties(found: dict | None, status: str = STATUSES[0]) -> dict:
    """Your columns, filled only when a job is first added."""
    people = (found or {}).get("people") or []
    contacts = "\n".join(
        " · ".join(filter(None, [p["name"], p.get("title", ""), p.get("linkedin", "")])) for p in people
    )
    return {"Status": {"select": {"name": status}}, "Contacts": _text(contacts)}


def create_row(client: Notion, database_id: str, job: dict, result: Result, fit: SkillFit | None,
               found: dict | None, status: str = STATUSES[0]) -> dict:
    """Add a job to the tracker: its scores, your starting columns, and the full ad as page content."""
    return client.request("POST", "pages", {
        "parent": {"database_id": database_id},
        "properties": {**tool_properties(job, result, fit), **starting_properties(found, status)},
        "children": description_blocks(job["description"]),
    })


def description_blocks(description: str) -> list[dict]:
    """The full ad as page content: a heading, then paragraphs under Notion's text cap."""
    chunks: list[str] = []
    for para in description.split("\n\n"):
        para = para.strip()
        while para:
            piece, para = para[:TEXT_LIMIT], para[TEXT_LIMIT:]
            if chunks and len(chunks[-1]) + len(piece) + 2 <= TEXT_LIMIT:
                chunks[-1] += "\n\n" + piece
            else:
                chunks.append(piece)
    heading = {"object": "block", "type": "heading_2",
               "heading_2": {"rich_text": [{"text": {"content": "Full job description"}}]}}
    return [heading] + [
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": c}}]}}
        for c in chunks[:99]  # Notion takes at most 100 blocks per request
    ]


# --------------------------------------------------------------------------
# Markdown -> Notion blocks (for research briefs)
# --------------------------------------------------------------------------

_INLINE = re.compile(r"\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^)\s]+)\)|(https?://[^\s)]+)")


def _rich(text: str) -> list[dict]:
    """Plain text with **bold**, [links](url) and bare https:// addresses as Notion rich text."""
    parts, at = [], 0
    for m in _INLINE.finditer(text):
        if m.start() > at:
            parts.append({"text": {"content": text[at:m.start()]}})
        if m.group(1):
            parts.append({"text": {"content": m.group(1)}, "annotations": {"bold": True}})
        elif m.group(2):
            parts.append({"text": {"content": m.group(2), "link": {"url": m.group(3)}}})
        else:
            parts.append({"text": {"content": m.group(4), "link": {"url": m.group(4)}}})
        at = m.end()
    if at < len(text):
        parts.append({"text": {"content": text[at:]}})
    for part in parts:
        part["text"]["content"] = part["text"]["content"][:TEXT_LIMIT]
    return parts


def markdown_blocks(markdown: str) -> list[dict]:
    """The Markdown a research brief uses: ## / ### headings, - and 1. lists, > quotes, paragraphs."""
    blocks = []
    for line in markdown.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            kind, text = "heading_3", line.lstrip("#").strip()
        elif line[:2] in ("- ", "* "):
            kind, text = "bulleted_list_item", line[2:]
        elif line.startswith(">"):
            kind, text = "quote", line.lstrip("> ").strip()
        elif re.match(r"\d+[.)] ", line):
            kind, text = "numbered_list_item", line.split(" ", 1)[1]
        else:
            kind, text = "paragraph", line
        blocks.append({"object": "block", "type": kind, kind: {"rich_text": _rich(text)}})
    return blocks


def append_blocks(client: Notion, page_id: str, blocks: list[dict]) -> None:
    for start in range(0, len(blocks), 100):  # Notion takes at most 100 per request
        client.request("PATCH", f"blocks/{page_id}/children", {"children": blocks[start:start + 100]})
