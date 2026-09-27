"""Renders scored jobs as one self-contained HTML page.

`render` is the plain calibration page for fixtures/ (score.py).
`render_dashboard` is the job list for pulled jobs (dashboard.py).
"""

from __future__ import annotations

from datetime import datetime
from html import escape

from . import contacts
from .ads import job_fact
from .scorer import Result
from .skills import SkillFit

CSS = """
:root { color-scheme: light dark; --bg:#faf9f7; --card:#fff; --ink:#1c1b19;
        --muted:#6b6862; --line:#e4e1db; --good:#1f7a4d; --warn:#9a6b00; --bad:#a33a2a; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#16151a; --card:#1e1d23; --ink:#eceaf0; --muted:#9b97a3;
          --line:#312f38; --good:#54c08a; --warn:#d9a53a; --bad:#e1806f; }
}
* { box-sizing: border-box; }
body { margin:0; padding:32px 20px 64px; background:var(--bg); color:var(--ink);
       font:15px/1.55 -apple-system,Segoe UI,system-ui,sans-serif; }
main { max-width: 860px; margin: 0 auto; }
h1 { font-size:22px; margin:0 0 4px; }
.sub { color:var(--muted); font-size:13px; margin:0 0 28px; }
h2 { font-size:14px; text-transform:uppercase; letter-spacing:.07em;
     color:var(--muted); margin:36px 0 12px; font-weight:600; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px;
        padding:16px 18px; margin-bottom:12px; }
.head { display:flex; gap:14px; align-items:baseline; justify-content:space-between; }
.title { font-weight:650; font-size:16px; }
.title a { color:inherit; text-decoration:none; border-bottom:1px solid var(--line); }
.score { font-size:26px; font-weight:700; white-space:nowrap; font-variant-numeric:tabular-nums; }
.s-high { color:var(--good); } .s-mid { color:var(--warn); } .s-low { color:var(--muted); }
.code { color:var(--muted); font-size:13px; margin:2px 0 12px; }
ul { margin:0 0 10px; padding-left:20px; }
li { margin:3px 0; }
.help::marker { color:var(--good); } .hurt::marker { color:var(--bad); }
.bars { display:grid; grid-template-columns:auto 1fr auto; gap:4px 10px;
        align-items:center; font-size:12.5px; color:var(--muted); margin:12px 0 4px; }
.track { background:var(--line); border-radius:3px; height:6px; }
.fill { background:var(--muted); border-radius:3px; height:6px; }
.q { color:var(--muted); font-size:13px; margin:8px 0 0; }
details { margin-top:12px; border-top:1px solid var(--line); padding-top:10px; }
summary { cursor:pointer; color:var(--muted); font-size:13px; }
pre { white-space:pre-wrap; font:13px/1.5 ui-monospace,Consolas,monospace;
      color:var(--muted); max-height:340px; overflow:auto; margin:10px 0 0; }
.skip { opacity:.8; }
.reason { color:var(--bad); font-weight:600; font-size:13.5px; }
.quote { color:var(--muted); font-size:12.5px; margin-top:4px; }
"""


def _band(total: int, high: int = 40, mid: int = 25) -> str:
    return "s-high" if total >= high else "s-mid" if total >= mid else "s-low"


def _explain(result: Result) -> str:
    """Why a job scored what it did: code, flags, reasons, bars, unknowns."""
    parts = [
        f'<div class="code">Likely code: {escape(result.likely_code)} · '
        f'{escape(result.confidence)} confidence</div>',
    ]
    for warning in result.flags:
        parts.append(f'<p class="reason">⚠ {escape(warning)}</p>')
    if result.helps:
        parts.append("<ul>" + "".join(
            f'<li class="help">{escape(h)}</li>' for h in result.helps) + "</ul>")
    if result.hurts:
        parts.append("<ul>" + "".join(
            f'<li class="hurt">{escape(h)}</li>' for h in result.hurts) + "</ul>")

    bars = []
    for c in result.components:
        pct = 0 if not c.max_points else 100 * c.points / c.max_points
        flag = " ❓" if c.unknown else ""
        points = f"{c.points:g}".rstrip()
        bars.append(
            f"<span>{escape(c.name)}{flag}</span>"
            f'<span class="track"><span class="fill" style="width:{pct:.0f}%;display:block"></span></span>'
            f'<span title="{escape(c.detail)}">{points}/{c.max_points:g}</span>'
        )
    parts.append(f'<div class="bars">{"".join(bars)}</div>')

    if result.unknowns:
        parts.append('<p class="q">❓ Unknowns: ' +
                     escape(", ".join(dict.fromkeys(result.unknowns))) + "</p>")
    for question in dict.fromkeys(result.questions):
        parts.append(f'<p class="q">Ask in interview: “{escape(question)}”</p>')
    return "".join(parts)


def _card(result: Result) -> str:
    ad = result.ad
    title = escape(ad.title)
    if ad.source:
        title = f'<a href="{escape(ad.source)}">{title}</a>'
    return (
        '<article class="card">'
        f'<div class="head"><div class="title">{title}</div>'
        f'<div class="score {_band(result.total)}">{result.total}'
        '<span style="font-size:13px;color:var(--muted)">/100</span></div></div>'
        f"{_explain(result)}"
        "<details><summary>Full job description</summary>"
        f"<pre>{escape(ad.description)}</pre></details></article>"
    )


def _skipped_card(result: Result) -> str:
    ad = result.ad
    title = escape(ad.title)
    if ad.source:
        title = f'<a href="{escape(ad.source)}">{title}</a>'
    reasons = "".join(
        f'<div class="reason">{escape(reason)}</div><div class="quote">…{escape(quote)}…</div>'
        for reason, quote in result.knockouts
    )
    return (
        '<article class="card skip">'
        f'<div class="head"><div class="title">{title}</div>'
        '<div class="score s-low">0</div></div>'
        f"{reasons}"
        "<details><summary>Full job description</summary>"
        f"<pre>{escape(ad.description)}</pre></details></article>"
    )


def render(results: list[Result], goal_name: str) -> str:
    scored = sorted((r for r in results if not r.skipped),
                    key=lambda r: r.total, reverse=True)
    skipped = [r for r in results if r.skipped]
    stamp = datetime.now().strftime("%d %b %Y, %H:%M")

    body = [
        "<main>",
        "<h1>Job Maxing — scored jobs</h1>",
        f'<p class="sub">Goal: {escape(goal_name)} · {len(scored)} scored, '
        f"{len(skipped)} skipped · {stamp}</p>",
    ]
    if scored:
        body.append(f"<h2>Scored ({len(scored)})</h2>")
        body += [_card(r) for r in scored]
    if skipped:
        body.append(f"<h2>Skipped — check these rules fired correctly ({len(skipped)})</h2>")
        body += [_skipped_card(r) for r in skipped]
    body.append("</main>")

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Job Maxing — scored jobs</title>"
        f"<style>{CSS}</style></head><body>{''.join(body)}</body></html>"
    )


# --------------------------------------------------------------------------
# the job list (pulled jobs, contacts attached)
# --------------------------------------------------------------------------

# What counts as "good". The colour bands, the summary tiles and the quick
# views all read these, so they always agree.
PR_GOOD, PR_OK = 40, 25
FIT_GOOD, FIT_OK = 60, 30

DASH_CSS = """
main { max-width: 1040px; }
:root { --accent:#3b5bdb; --good-bg:#e6f4ec; --warn-bg:#fbf1dc; --bad-bg:#fbe9e6; --chip:#f1efeb; }
@media (prefers-color-scheme: dark) {
  :root { --accent:#8ea2ff; --good-bg:#16301f; --warn-bg:#352a12; --bad-bg:#3a1d19; --chip:#28262e; }
}
header.top { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 16px; margin-bottom:18px; }
header.top h1 { margin:0; }
header.top .sub { margin:0; }
header.top .tracker { margin-left:auto; }
header.top .tracker + #pull { margin-left:0; }
#pull { margin-left:auto; cursor:pointer; font:inherit; font-size:13px; }
#pull:disabled { opacity:.6; cursor:progress; }
.add-job { display:flex; gap:8px; margin:0 0 14px; font-size:13.5px; }
.add-job input { flex:1 1 auto; min-width:0; padding:7px 11px; font:inherit;
            border:1px solid var(--line); border-radius:8px; background:var(--card); color:var(--ink); }
.add-job button { cursor:pointer; font:inherit; font-size:13px; white-space:nowrap; }
.add-job button:disabled { opacity:.6; cursor:progress; }
.pulling { background:var(--card); border:1px solid var(--line); border-radius:12px;
           padding:12px 14px; margin:0 0 14px; }
.pull-status { margin:0 0 8px; font-size:13.5px; }
.pulling progress { width:100%; height:8px; accent-color:var(--accent); }
.pull-log { font-size:12px; color:var(--muted); max-height:180px; overflow:auto;
            margin:8px 0 0; white-space:pre-wrap; }
.tiles { display:grid; grid-template-columns:repeat(4, 1fr); gap:10px; margin:0 0 14px; }
.tile { text-align:left; font:inherit; color:var(--ink); background:var(--card); cursor:pointer;
        border:1px solid var(--line); border-radius:12px; padding:12px 14px; }
.tile:hover { border-color:var(--muted); }
.tile[aria-pressed=true] { border-color:var(--accent); box-shadow:0 0 0 1px var(--accent) inset; }
.tile b { display:block; font-size:26px; line-height:1.1; font-variant-numeric:tabular-nums; }
.tile span { color:var(--muted); font-size:12.5px; }
.legend { color:var(--muted); font-size:13px; margin:0 0 16px; line-height:1.7; }
.legend b { color:var(--ink); font-weight:600; }
.dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin:0 3px 0 8px; vertical-align:0; }
.controls { display:flex; flex-wrap:wrap; gap:10px 14px; align-items:center;
            background:var(--card); border:1px solid var(--line); border-radius:12px;
            padding:10px 12px; margin:0 0 14px; font-size:13.5px; position:sticky; top:8px; z-index:2;
            box-shadow:0 4px 14px rgba(0,0,0,.06); }
.controls label { display:flex; gap:6px; align-items:center; color:var(--muted); }
.controls input[type=search] { flex:1 1 220px; min-width:0; padding:7px 11px; font:inherit;
            border:1px solid var(--line); border-radius:8px; background:var(--bg); color:var(--ink); }
.controls select { font:inherit; padding:5px 8px; border-radius:8px;
            border:1px solid var(--line); background:var(--bg); color:var(--ink); }
.count { margin-left:auto; color:var(--muted); white-space:nowrap; }
:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }

details.job { background:var(--card); border:1px solid var(--line); border-radius:12px; margin:0 0 8px; }
details.job:hover { border-color:var(--muted); }
details.job[open] { border-color:var(--muted); }
details.job > summary { list-style:none; display:grid; grid-template-columns:auto 1fr auto 18px;
              gap:14px; align-items:center; padding:12px 14px; cursor:pointer; border-radius:12px; color:var(--ink); }
details.job > summary::-webkit-details-marker { display:none; }
details.job[open] > summary { border-bottom:1px solid var(--line); border-radius:12px 12px 0 0; }
.chev { color:var(--muted); transition:transform .15s; font-size:13px; }
details.job[open] .chev { transform:rotate(90deg); }
.pills { display:flex; gap:6px; }
.pill { width:54px; border-radius:9px; text-align:center; padding:5px 0 4px; background:var(--chip); }
.pill b { display:block; font-size:19px; line-height:1.1; font-variant-numeric:tabular-nums; }
.pill small { display:block; font-size:10px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }
.pill.s-high { background:var(--good-bg); } .pill.s-mid { background:var(--warn-bg); }
.pill.s-high b { color:var(--good); } .pill.s-mid b { color:var(--warn); } .pill.s-low b { color:var(--muted); }
.role { font-weight:650; font-size:15.5px; }
.meta { color:var(--muted); font-size:13px; margin-top:2px; }
.meta .money { color:var(--ink); font-weight:600; }
.tags { display:flex; flex-wrap:wrap; gap:5px; justify-content:flex-end; }
.tag { font-size:11.5px; border:1px solid var(--line); border-radius:999px; padding:1px 8px;
       color:var(--muted); white-space:nowrap; }
.tag.warn { color:var(--warn); border-color:currentColor; }
.tag.bad { color:var(--bad); border-color:currentColor; }

.body { padding:16px; }
.cols { display:grid; grid-template-columns:1.35fr 1fr; gap:26px; }
.panel h3 { font-size:12px; text-transform:uppercase; letter-spacing:.07em; color:var(--muted);
            margin:0 0 8px; font-weight:600; }
.panel section + section { margin-top:18px; }
.chips { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 8px; }
.chip { font-size:12.5px; border-radius:999px; padding:2px 10px; background:var(--chip); cursor:help; }
.chip.have { background:var(--good-bg); color:var(--good); }
.chip.part { background:var(--warn-bg); color:var(--warn); }
.chip.miss { background:var(--bad-bg); color:var(--bad); }
.chip-label { font-size:12px; color:var(--muted); margin:0 0 4px; }
.actions { display:flex; flex-wrap:wrap; gap:8px; }
.btn { font-size:13px; text-decoration:none; color:var(--ink); border:1px solid var(--line);
       border-radius:8px; padding:6px 12px; background:var(--bg); }
.btn:hover { border-color:var(--muted); }
.btn.primary { background:var(--accent); border-color:var(--accent); color:var(--bg); font-weight:600; }
.person { margin:0 0 10px; font-size:13.5px; }
.person a { color:inherit; font-weight:600; }
.person .t { color:var(--muted); }
.none { color:var(--muted); font-size:13.5px; }
.body details { margin-top:16px; }
.empty { text-align:center; color:var(--muted); padding:30px 0; }
.empty button { font:inherit; color:var(--accent); background:none; border:0; cursor:pointer; text-decoration:underline; }
details.skipped { margin-top:30px; }
details.skipped > summary { font-size:14px; color:var(--muted); padding:8px 0; border-top:1px solid var(--line); }
details.skipped > summary b { color:var(--ink); }
details.skipped details.job { opacity:.85; }

@media (max-width: 720px) {
  body { padding:20px 16px 48px; }
  .tiles { grid-template-columns:repeat(2, 1fr); }
  .cols { grid-template-columns:1fr; }
  details.job > summary { grid-template-columns:auto 1fr 14px; }
  .tags { grid-column:1 / -1; grid-row:2; justify-content:flex-start; }
  .count { margin-left:0; }
}
"""

DASH_JS = """
const $ = id => document.getElementById(id);
const q = $('q'), src = $('src'), agency = $('agency'), sort = $('sort'),
      count = $('count'), list = $('scored'), empty = $('empty'),
      tiles = [...document.querySelectorAll('.tile[data-view]')];
let view = 'all';
const views = {
  all: d => true,
  top: d => +d.score >= PR_GOOD,
  both: d => +d.score >= PR_GOOD && +d.fit >= FIT_GOOD,
};
function apply() {
  const words = q.value.toLowerCase().trim();
  let shown = 0;
  document.querySelectorAll('[data-job]').forEach(el => {
    const d = el.dataset, scored = d.scored === '1';
    const ok = (!words || d.text.includes(words))
      && (src.value === 'all' || d.source === src.value)
      && (!agency.checked || d.agency !== '1')
      && (!scored || views[view](d));
    el.hidden = !ok;
    if (scored && ok) shown++;
  });
  count.textContent = shown + ' of ' + list.children.length + ' jobs';
  empty.hidden = shown > 0;
}
function order() {
  const key = sort.value;
  [...list.children].sort((a, b) => b.dataset[key] - a.dataset[key] || b.dataset.score - a.dataset.score)
    .forEach(el => list.appendChild(el));
}
function setView(v) {
  view = v;
  tiles.forEach(t => t.setAttribute('aria-pressed', t.dataset.view === v));
  apply();
}
tiles.forEach(t => t.addEventListener('click', () => {
  if (t.dataset.view === 'skipped') { const s = $('skipped'); s.open = true; s.scrollIntoView({behavior: 'smooth'}); return; }
  setView(t.dataset.view);
}));
$('reset').addEventListener('click', () => { q.value = ''; src.value = 'all'; agency.checked = false; setView('all'); });
[q, src, agency].forEach(el => el.addEventListener('input', apply));
sort.addEventListener('input', order);
setView('all');

// "Pull latest jobs": only works when the page is opened by app.py (which runs the pull).
const pullBtn = $('pull'), panel = $('pulling'), status = $('pull-status'),
      bar = $('pull-bar'), log = $('pull-log'), addForm = $('add-job'), addBtn = $('add-btn');
let since = 0;
function showPull(text) { panel.hidden = false; status.textContent = text; }
function busy(on) { pullBtn.disabled = addBtn.disabled = on; }
async function watch() {
  const p = await (await fetch('/progress?since=' + since)).json();
  since = p.next;
  if (p.lines.length) { log.textContent += p.lines.join('\\n') + '\\n'; log.scrollTop = log.scrollHeight; }
  if (p.running) {
    busy(true);
    // Each step fills its share of the bar. The pull reports how many jobs have arrived;
    // steps that can't tell show half done.
    const done = p.steps ? (p.step - 1 + (p.part ?? 0.5)) / p.steps : 0;
    bar.value = done;
    const clock = Math.floor(p.elapsed / 60) + ':' + String(p.elapsed % 60).padStart(2, '0');
    showPull((p.steps ? `Step ${p.step} of ${p.steps}: ${p.name}` : 'Starting')
             + (p.detail ? ` · ${p.detail}` : '') + ` · ${Math.round(done * 100)}% · ${clock}`);
    setTimeout(watch, 1000);
  } else if (p.failed) {
    bar.value = 1;
    if (p.failed.length) {
      busy(false);
      showPull('Finished, but failed: ' + p.failed.join(', ') + '. Details below.');
    } else {
      showPull('Done. Loading the new list…');
      setTimeout(() => location.reload(), 1200);
    }
  }
}
pullBtn.addEventListener('click', async () => {
  if (location.protocol === 'file:') {
    showPull('This button needs the app running. In the project folder, run: python app.py');
    return;
  }
  start('/pull');
});
// "Add job": paste a link, the app reads the ad and adds it (then Notion + rebuild, like a pull).
addForm.addEventListener('submit', e => {
  e.preventDefault();
  if (location.protocol === 'file:') {
    showPull('Adding a job needs the app running. In the project folder, run: python app.py');
    return;
  }
  start('/add', JSON.stringify({url: $('add-url').value}));
});
async function start(path, body) {
  busy(true); log.textContent = ''; since = 0;
  showPull('Starting…');
  try {
    const r = await fetch(path, {method: 'POST', body,
      headers: body ? {'X-Jobmax': '1', 'Content-Type': 'application/json'} : {'X-Jobmax': '1'}});
    if (r.status === 400) { busy(false); showPull((await r.json()).error); return; }
    if (r.status === 409) showPull('Already running. Following it…');
    watch();
  } catch (e) {
    busy(false);
    showPull('Could not reach the app. Is python app.py still running?');
  }
}
// Reopened the page mid-pull? Pick the progress back up.
if (location.protocol !== 'file:') fetch('/progress').then(r => r.json()).then(p => { if (p.running) watch(); });
"""

_STATES = {
    "New South Wales": "NSW", "Victoria": "VIC", "Queensland": "QLD", "Western Australia": "WA",
    "South Australia": "SA", "Tasmania": "TAS", "Australian Capital Territory": "ACT",
    "Northern Territory": "NT",
}


def _place(location: str) -> str:
    """'Sydney, New South Wales, Australia' -> 'Sydney NSW'."""
    parts = [p.strip() for p in location.split(",") if p.strip() and p.strip() != "Australia"]
    if len(parts) >= 2 and parts[-1] in _STATES:
        return f"{parts[0]} {_STATES[parts[-1]]}"
    return ", ".join(parts)


def _applicants(value: str) -> str:
    """Board wording -> short form: 'Over 200 applicants' -> '200+ applicants'."""
    value = value.strip()
    if value.isdigit():
        return f"{value} applicants"
    low = value.lower()
    if low.startswith("over "):
        return value[5:].split()[0] + "+ applicants"
    if "first" in low:
        return "<" + "".join(ch for ch in value if ch.isdigit()) + " applicants"
    return value


def _days(posted: str) -> int | None:
    try:
        return max(0, (datetime.now() - datetime.fromisoformat(posted[:10])).days)
    except ValueError:
        return None


def _pill(value: int | None, label: str, good: int, ok: int, tip: str) -> str:
    if value is None:
        return f'<div class="pill s-low" title="{escape(tip)}"><b>–</b><small>{label}</small></div>'
    return (f'<div class="pill {_band(value, good, ok)}" title="{escape(tip)}">'
            f"<b>{value}</b><small>{label}</small></div>")


def _people(job: dict, found: dict | None, contact_mix: list[dict]) -> str:
    """People already found (if any), then LinkedIn searches to find them yourself."""
    searches = "".join(
        f'<a class="btn" href="{escape(url)}" target="_blank" rel="noopener">{escape(label)} ↗</a>'
        for label, url in contacts.search_links(job["company"], contact_mix, contacts.company_link(job)))
    rows = []
    for p in (found or {}).get("people") or []:
        name = escape(p["name"])
        if p.get("linkedin"):
            name = f'<a href="{escape(p["linkedin"])}">{name}</a>'
        email = f' · {escape(p["email"])}' if p.get("email") else ""
        rows.append(f'<p class="person">{name} <span class="t">· {escape(p.get("targeted_as", ""))}</span>'
                    f'<br><span class="t">{escape(p.get("title", ""))}{email}</span></p>')
    hint = ("Find more on LinkedIn:" if rows else
            "Search LinkedIn, pick 3 people, then add them to Contacts in Notion.")
    return "".join(rows) + f'<p class="none">{hint}</p><div class="actions">{searches}</div>'


def _skills(fit: SkillFit | None) -> str:
    if fit is None:
        return '<p class="none">No skills profile (profile/skills.yaml).</p>'
    if fit.score is None:
        return '<p class="none">The ad names none of the skills in your profile.</p>'
    groups = [("have", "You have", fit.have), ("part", "Partly", fit.partial), ("miss", "Missing", fit.missing)]
    out = []
    for cls, label, hits in groups:
        if not hits:
            continue
        chips = "".join(
            f'<span class="chip {cls}" title="{escape(f"Ad says: “{h.quote}”" + (f" · Proof: {h.evidence}" if h.evidence else ""))}">'
            f"{escape(h.name)}</span>" for h in hits)
        out.append(f'<p class="chip-label">{label}</p><div class="chips">{chips}</div>')
    return "".join(out)


def _job_row(job: dict, result: Result, found: dict | None, agency: bool,
             fit: SkillFit | None, tracker_page: str = "", contact_mix: list[dict] = ()) -> str:
    salary = job_fact(job["description"], "Salary")
    days = _days(job.get("posted", ""))
    meta = " · ".join(filter(None, [
        escape(job["company"]),
        escape(_place(job.get("location", ""))),
        f'<span class="money">{escape(salary)}</span>' if salary else "",
        "" if days is None else ("posted today" if days == 0 else f"{days}d ago"),
        escape(_applicants(job.get("applicants", ""))),
        escape(job["source"].capitalize()),
    ]))

    tags = []
    if result.skipped:
        tags.append(f'<span class="tag bad">{escape(result.knockouts[0][0])}</span>')
    if agency:
        tags.append('<span class="tag" title="Recruitment agency: the real employer is hidden">agency</span>')
    if result.flags:
        tags.append(f'<span class="tag warn" title="{escape("; ".join(result.flags))}">⚠ check</span>')
    if not result.skipped and result.confidence == "low":
        tags.append('<span class="tag" title="The ad doesn\'t say which team. Ask in interview.">team unclear</span>')

    research = job.get("company_research") or {}
    links = [(job.get("url"), "Open job ad", "btn primary"), (tracker_page, "Track in Notion", "btn"),
             (job.get("apply_url"), "Apply", "btn"),
             (research.get("linkedin"), "Company LinkedIn", "btn"), (research.get("website"), "Website", "btn")]
    seen, buttons = set(), []
    for url, label, cls in links:
        if url and url not in seen:  # LinkedIn's apply link is often the ad itself
            seen.add(url)
            buttons.append(f'<a class="{cls}" href="{escape(url)}" target="_blank" rel="noopener">{label}</a>')

    if result.skipped:
        why = "".join(f'<div class="reason">{escape(r)}</div><div class="quote">…{escape(q)}…</div>'
                      for r, q in result.knockouts)
    else:
        why = _explain(result)
    skill_score = fit.score if fit else None
    pills = (_pill(0 if result.skipped else result.total, "PR", PR_GOOD, PR_OK,
                   "PR score: how much this job helps your PR (ANZSCO fit, sponsorship, salary, type)")
             + _pill(skill_score, "Skills", FIT_GOOD, FIT_OK,
                     "Skills fit: how much of what the ad asks for you can prove"))

    text = f'{job["company"]} {job["role"]} {job.get("location", "")}'.lower()
    return (
        f'<details class="job" data-job data-scored="{0 if result.skipped else 1}" '
        f'data-score="{result.total}" data-fit="{-1 if skill_score is None else skill_score}" '
        f'data-new="{-(days if days is not None else 9999)}" data-source="{escape(job["source"])}" '
        f'data-agency="{1 if agency else 0}" data-text="{escape(text)}">'
        f'<summary><div class="pills">{pills}</div>'
        f'<div><div class="role">{escape(job["role"])}</div><div class="meta">{meta}</div></div>'
        f'<div class="tags">{"".join(tags)}</div><span class="chev" aria-hidden="true">▶</span></summary>'
        '<div class="body"><div class="cols">'
        f'<div class="panel"><section><h3>{"Why it was skipped" if result.skipped else "Why this PR score"}</h3>{why}</section>'
        f'<section><h3>Skills fit</h3>{_skills(fit)}</section></div>'
        f'<div class="panel"><section><div class="actions">{"".join(buttons)}</div></section>'
        f'<section><h3>People to contact</h3>{_people(job, found, contact_mix)}</section></div>'
        "</div><details><summary>Full job description</summary>"
        f'<pre>{escape(job["description"])}</pre></details></div></details>'
    )


def render_dashboard(rows: list[tuple[dict, Result, dict | None, bool, SkillFit | None]],
                     goal_name: str, tracker_url: str = "", tracker_pages: dict[str, str] | None = None,
                     contact_mix: list[dict] = ()) -> str:
    """rows: (job record, its score, its company's contacts or None, is agency, skills fit).

    tracker_pages maps a job key to its Notion page (from the last sync).
    contact_mix is the goal file's contacts.mix, for the LinkedIn search buttons.
    """
    pages = tracker_pages or {}
    scored = sorted((r for r in rows if not r[1].skipped), key=lambda r: -r[1].total)
    skipped = [r for r in rows if r[1].skipped]
    sources = sorted({r[0]["source"] for r in rows})
    stamp = datetime.now().strftime("%d %b %Y, %H:%M")

    top = sum(1 for r in scored if r[1].total >= PR_GOOD)
    both = sum(1 for r in scored if r[1].total >= PR_GOOD and r[4] and (r[4].score or 0) >= FIT_GOOD)
    tiles = [("all", len(scored), "jobs to look at"), ("top", top, f"top picks · PR {PR_GOOD}+"),
             ("both", both, f"strong on both · skills {FIT_GOOD}+"), ("skipped", len(skipped), "skipped by rules")]
    tiles_html = "".join(
        f'<button class="tile" data-view="{v}" aria-pressed="false"><b>{n}</b><span>{label}</span></button>'
        for v, n, label in tiles)

    options = "".join(f'<option value="{escape(s)}">{escape(s.capitalize())}</option>' for s in sources)
    body = [
        "<main>",
        '<header class="top"><h1>Job Maxing</h1>'
        f'<p class="sub">Goal: {escape(goal_name)} · updated {stamp}</p>'
        + (f'<a class="btn tracker" href="{escape(tracker_url)}" target="_blank" rel="noopener">'
           "Open tracker in Notion ↗</a>" if tracker_url else "")
        + '<button class="btn primary" id="pull" type="button">Pull latest jobs</button>'
        + "</header>",
        '<form class="add-job" id="add-job">'
        '<input type="url" id="add-url" required aria-label="Job link" '
        'placeholder="Paste a job link to add it: Seek, LinkedIn or a company careers page">'
        '<button class="btn" id="add-btn" type="submit">Add job</button></form>',
        '<section class="pulling" id="pulling" hidden aria-live="polite">'
        '<p class="pull-status" id="pull-status"></p>'
        '<progress id="pull-bar" max="1" value="0"></progress>'
        '<pre class="pull-log" id="pull-log"></pre></section>',
        f'<div class="tiles">{tiles_html}</div>',
        '<p class="legend"><b>PR</b> = how much the job helps your PR (out of 100). '
        "<b>Skills</b> = how much of what the ad asks for you can prove. "
        f'<span class="dot" style="background:var(--good)"></span>good (PR {PR_GOOD}+ / skills {FIT_GOOD}+)'
        f'<span class="dot" style="background:var(--warn)"></span>okay'
        '<span class="dot" style="background:var(--muted)"></span>weak. '
        "Click a job to see why. Hover a score or skill for detail.</p>",
        '<div class="controls">'
        '<input type="search" id="q" placeholder="Search company, role or city" aria-label="Search">'
        '<label>Sort <select id="sort"><option value="score">PR score</option>'
        '<option value="fit">Skills fit</option><option value="new">Newest</option></select></label>'
        f'<label>Board <select id="src"><option value="all">All</option>{options}</select></label>'
        '<label><input type="checkbox" id="agency"> Hide agencies</label>'
        '<span class="count" id="count"></span></div>',
        '<div id="scored">' + "".join(_job_row(*r, pages.get(r[0]["key"], ""), contact_mix) for r in scored) + "</div>",
        '<p class="empty" id="empty" hidden>No jobs match. <button id="reset">Show all jobs</button></p>',
    ]
    if skipped:
        body.append(
            '<details class="skipped" id="skipped"><summary><b>Skipped by the rules '
            f"({len(skipped)})</b>: open to check each rule fired correctly</summary>"
            + "".join(_job_row(*r, pages.get(r[0]["key"], ""), contact_mix) for r in skipped) + "</details>")
    body.append("</main>")

    constants = f"const PR_GOOD = {PR_GOOD}, FIT_GOOD = {FIT_GOOD};"
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Job Maxing</title>"
        f"<style>{CSS}{DASH_CSS}</style></head><body>{''.join(body)}"
        f"<script>{constants}{DASH_JS}</script></body></html>"
    )
