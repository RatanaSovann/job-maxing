"""Company research + artifact ideas for one job, using Claude with web search.

The output is a short brief in Markdown (## headings, - bullets, [links](url)),
which notion.markdown_blocks turns into Notion blocks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import anthropic

from .scorer import Result
from .skills import SkillProfile

MODEL = "claude-opus-5"
MAX_SEARCHES = 8          # web searches per company (2 of them for finding people); the main cost lever after tokens
MAX_CONTINUATIONS = 5     # resumes of a long server-side search turn (pause_turn)

# For the cost line printed after each company. Claude Opus 5 list prices.
PRICE_IN, PRICE_OUT = 5.00 / 1e6, 25.00 / 1e6     # per token
PRICE_SEARCH = 10.00 / 1000                       # per web search

SYSTEM = """You research one company for a job seeker and write a short, practical brief.

The job seeker's strategy: pick a company they like, find a real gap or pain point,
build one small artifact that shows they can solve it (a mini audit, a dashboard
mock-up, a process map, a strategy rewrite), then send it to ~3 people there.
Your brief is the starting point for that artifact.

Use web search for the company's recent news, annual or investor reports, product
changes, customer reviews, and what their other job ads say. Prefer the last 12
months. Everything you state about the company must come from the job ad or from
a source you link; if you found little, say so plainly rather than filling gaps.
The artifact must be buildable in a weekend from public information, by this person,
with the skills listed.

Write in plain Australian English, short sentences, no jargon without a brief
definition. Use exactly these sections, as Markdown:

## Snapshot
3-5 bullets: what they do, size, and what is changing for them right now. Link sources.
## Likely pain points
2-3 bullets. Each: the problem, the evidence (quote the ad or link a source), and why
this role exists to fix it.
## Artifact ideas
3 bullets, best first. Each: **name of the artifact**, what it contains, which pain
point it addresses, which of the person's skills it shows, and the public data to use.
## Who to send it to
Exactly the number of people asked for in <who_to_find>, as one bullet each:
**Name**, their job title — why them, what to send or ask them, and a [source](url)
showing they work there now. Fill the list in this order:
1. People in <people_you_know> (already connected: ask for an introduction, the team's
   real problems, or a referral).
2. Suitable people from <contacts>.
3. People you find with web search: the company's leadership or team page, recent news,
   conference talks, articles they wrote, or LinkedIn profiles that appear in search
   results. Pick titles like the ones in <who_to_find> and never the excluded ones.
Only name a person a source shows at this company; never guess a name or an email.
If you can't find enough, say how many are missing and which job titles to search
for on LinkedIn instead.
## Opening line
One or two sentences for a first LinkedIn message, following the outreach rules.
## Sources
Bullet list of the links you used."""


@dataclass
class Brief:
    markdown: str
    cost_usd: float
    searches: int
    results: int     # web pages the searches actually returned
    model: str


def _search_outcomes(content) -> tuple[int, list[str]]:
    """(results returned, error codes) across the web search blocks of one response.

    Search errors don't raise: they come back as a result block whose content is
    an error object instead of a list.
    """
    results, errors = 0, []
    for block in content:
        if block.type != "web_search_tool_result":
            continue
        if isinstance(block.content, list):
            results += len(block.content)
        else:
            errors.append(getattr(block.content, "error_code", "unknown"))
    return results, errors


def _skills_text(profile: SkillProfile | None) -> str:
    if profile is None:
        return "(no skills profile)"
    lines = [f'- {s["name"]} ({s["level"]}): {s.get("evidence", "")}'
             for s in profile.skills if s["level"] != "none"]
    return "\n".join(lines) or "(none listed)"


def _wanted_text(mix: list[dict], exclude: list[str]) -> str:
    groups = [f'- {g.get("wanted", 1)} × {g["role"]}, titles like: {", ".join(g.get("titles", []))}'
              for g in mix if g.get("wanted")]
    if not groups:
        return "- 3 people: whoever owns the problem this role solves, and someone doing the job now"
    return "\n".join(groups + ([f'Excluded titles (ICT, wrong world): {", ".join(exclude)}'] if exclude else []))


def build_prompt(job: dict, result: Result, profile: SkillProfile | None,
                 contacts: str, outreach_rules: list[str], known: str = "",
                 mix: list[dict] = (), exclude_titles: list[str] = ()) -> str:
    why = "\n".join([f"+ {h}" for h in result.helps] + [f"- {h}" for h in result.hurts])
    rules = "\n".join(f"- {r}" for r in outreach_rules) or "(none)"
    return f"""Today is {date.today():%d %B %Y}.

<job>
Company: {job["company"]}
Role: {job["role"]}
Location: {job.get("location", "")}
Company website: {(job.get("company_research") or {}).get("website", "") or "unknown"}
Likely team / occupation code: {result.likely_code} ({result.confidence} confidence)
What the ad signals:
{why or "(nothing notable)"}

Full ad:
{job["description"]}
</job>

<my_skills>
{_skills_text(profile)}
</my_skills>

<contacts>
{contacts.strip() or "(none found yet)"}
</contacts>

<people_you_know>
{known.strip() or "(no LinkedIn connections at this company)"}
</people_you_know>

<who_to_find>
{_wanted_text(mix, exclude_titles)}
</who_to_find>

<outreach_rules>
{rules}
</outreach_rules>

Research {job["company"]} and write the brief."""


def people_from(markdown: str) -> str:
    """The brief's "Who to send it to" bullets as plain lines, for Notion's Contacts column.

    '- **Jo Lee**, Head of Finance — why… [source](https://x)' -> 'Jo Lee, Head of Finance — why… (https://x)'
    """
    section = re.search(r"^## Who to send it to\s*$(.*?)(?=^## |\Z)", markdown, re.M | re.S)
    lines = []
    for line in (section.group(1) if section else "").splitlines():
        if m := re.match(r"\s*(?:[-*]|\d+\.)\s+(.*)", line):
            text = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", r"\1 (\2)", m.group(1))
            lines.append(text.replace("**", "").strip())
    return "\n".join(lines)


def research(client: anthropic.Anthropic, prompt: str) -> Brief:
    """One company, one brief. Resumes long search turns; raises on a refusal."""
    messages = [{"role": "user", "content": prompt}]
    tokens_in = tokens_out = searches = results = 0
    errors: list[str] = []
    for _ in range(MAX_CONTINUATIONS + 1):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=SYSTEM,
            messages=messages,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCHES,
                    "user_location": {"type": "approximate", "country": "AU", "city": "Sydney"}}],
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            # If a safety check declines, the API retries on a fallback model itself.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            response = stream.get_final_message()

        usage = response.usage
        tokens_in += (usage.input_tokens + (usage.cache_creation_input_tokens or 0)
                      + (usage.cache_read_input_tokens or 0))
        tokens_out += usage.output_tokens
        if usage.server_tool_use:
            searches += usage.server_tool_use.web_search_requests or 0
        found, failed = _search_outcomes(response.content)
        results += found
        errors += failed

        if response.stop_reason == "pause_turn":
            # Long search turn: send it back and the server carries on.
            messages = [messages[0], {"role": "assistant", "content": response.content}]
            continue
        if response.stop_reason == "refusal":
            raise RuntimeError(f"Claude declined this one ({getattr(response.stop_details, 'category', None)}).")
        break
    else:
        raise RuntimeError("Search kept going past the continuation limit; nothing written.")

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if response.stop_reason == "max_tokens" or "## Snapshot" not in text:
        raise RuntimeError(f"Brief came back incomplete (stop reason: {response.stop_reason}); nothing written.")
    cost = tokens_in * PRICE_IN + tokens_out * PRICE_OUT + searches * PRICE_SEARCH
    if not results:
        # A brief from the job ad alone looks like research but isn't. Don't write it.
        raise RuntimeError(f"web search returned nothing (errors: {', '.join(errors) or 'none reported'}; "
                           f"about ${cost:.2f} spent); nothing written.")
    return Brief(text[text.index("## Snapshot"):], round(cost, 3), searches, results, response.model)
