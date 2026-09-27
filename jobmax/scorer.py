"""Applies a goal rubric to a job ad.

Every threshold, phrase and weight comes from the goal YAML file. Nothing in
here is specific to Australian PR, so a second goal file needs no code change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .ads import Ad


# --------------------------------------------------------------------------
# phrase matching
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Match:
    phrase: str      # the phrase from the rubric
    quote: str       # what the ad actually says (kept for the job card)
    context: str     # the sentence-ish window around it
    start: int
    end: int


def _pattern(phrase: str) -> re.Pattern:
    """Turn a rubric phrase into a regex.

    - spaces match any run of whitespace, so line breaks inside a phrase are fine
    - a trailing `*` means prefix match ("epidemiolog*" -> "epidemiology")
    - otherwise a trailing "s" is tolerated ("sprint" -> "sprints")
    - "api" never matches inside "capital": the edges are word boundaries
    """
    prefix = phrase.endswith("*")
    body = phrase[:-1] if prefix else phrase
    core = r"\s+".join(re.escape(word) for word in body.split())
    if prefix:
        tail = r"\w*"
    elif body[-1:].isalpha() and not body.endswith("s"):
        tail = r"s?"
    else:
        tail = ""
    return re.compile(rf"(?<!\w){core}{tail}(?!\w)", re.IGNORECASE)


def find(text: str, phrases: list[str], window: int = 70) -> list[Match]:
    """All rubric phrases present in the text, one hit per phrase, overlaps dropped.

    Overlaps are dropped so "non-functional requirements" is not also counted as
    "functional requirements".
    """
    hits: list[Match] = []
    for phrase in phrases:
        m = _pattern(str(phrase)).search(text)
        if not m:
            continue
        left = max(0, m.start() - window)
        context = " ".join(text[left : m.end() + window].split())
        hits.append(Match(str(phrase), m.group(0), context, m.start(), m.end()))

    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    kept: list[Match] = []
    for hit in hits:
        if kept and hit.start < kept[-1].end:
            continue
        kept.append(hit)
    return kept


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------

@dataclass
class Component:
    name: str
    points: float
    max_points: float
    detail: str = ""
    unknown: bool = False


@dataclass
class Result:
    ad: Ad
    total: int = 0
    components: list[Component] = field(default_factory=list)
    knockouts: list[tuple[str, str]] = field(default_factory=list)  # (reason, quoted context)
    likely_code: str = ""
    confidence: str = ""
    helps: list[str] = field(default_factory=list)
    hurts: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)  # warnings, no points

    @property
    def skipped(self) -> bool:
        return bool(self.knockouts)


# --------------------------------------------------------------------------
# the rubric
# --------------------------------------------------------------------------

class Rubric:
    def __init__(self, config: dict, path: Path | None = None):
        self.config = config
        self.path = path
        self.name = config.get("goal", {}).get("name", "unnamed goal")

    @classmethod
    def load(cls, path: Path) -> "Rubric":
        return cls(yaml.safe_load(path.read_text(encoding="utf-8-sig")), path)

    # -- step 1 ------------------------------------------------------------
    def _knockouts(self, ad: Ad) -> list[tuple[str, str]]:
        """Reasons this ad is a hard no, each with the phrase quoted in context.

        `role_phrases` are searched in the job title only. "Internship" in the
        title means the job is unpaid; in the body it is usually the candidate's
        own past experience.

        `ignore_phrases` are blanked out before searching, so "working with
        local government" (a client) does not fire the government rule.

        `salary_above` fires when the stated salary's midpoint is higher.
        """
        found = []
        for rule in self.config.get("knockouts", []):
            text = ad.text
            for ignored in find(text, rule.get("ignore_phrases", [])):
                text = text[:ignored.start] + " " * (ignored.end - ignored.start) + text[ignored.end:]
            hits = (find(text, rule.get("phrases", []))
                    or find(ad.role, rule.get("role_phrases", [])))
            if hits:
                found.append((rule["reason"], hits[0].context))
            elif "salary_above" in rule:
                amount = parse_salary(ad.description)
                if amount is not None and amount > rule["salary_above"]:
                    found.append((rule["reason"], f"salary ${amount:,.0f} is above ${rule['salary_above']:,.0f}"))
        return found

    def _flags(self, ad: Ad) -> list[str]:
        """Warnings worth seeing on the card. They never change the score."""
        return [f'{flag["note"]} ({_quoted(hits)})'
                for flag in self.config.get("flags", [])
                if (hits := find(ad.text, flag.get("phrases", [])))]

    # -- ANZSCO fit --------------------------------------------------------
    def _anzsco(self, ad: Ad, result: Result) -> Component:
        cfg = self.config["anzsco"]
        codes = cfg.get("codes", {})
        text = ad.text
        max_points = cfg["max_points"]

        off = cfg.get("off_target_titles", {})
        title_hits = find(ad.role, off.get("phrases", []))
        if title_hits:
            base = off["points"]
            code = off.get("code", "no target-code match")
            confidence = off.get("confidence", "medium")
            basis = f'title says "{title_hits[0].quote}" — not analyst work under any target code'
            result.hurts.append(basis)
        else:
            for team in cfg.get("teams", []):
                hits = find(text, team.get("phrases", []))
                if hits:
                    base = team["points"]
                    code = codes.get(team.get("code_ref"), team["id"])
                    confidence = team.get("confidence", "medium")
                    basis = f'{team["label"]}: "{hits[0].quote}"'
                    (result.hurts if team["id"] == "ict" else result.helps).append(basis)
                    break
            else:
                no_team = cfg["no_team"]
                base = no_team["points"]
                code = codes.get(no_team.get("code_ref"), "")
                confidence = no_team.get("confidence", "low")
                basis = "no team named in the ad — not guessing"
                result.unknowns.append("which team the role sits in")
                question = self.config.get("questions", {}).get("team_unclear")
                if question:
                    result.questions.append(question)

        language = cfg.get("language", {})
        up_cfg, down_cfg = language.get("raise", {}), language.get("lower", {})
        up_hits = find(text, up_cfg.get("phrases", []))
        down_hits = find(text, down_cfg.get("phrases", []))
        up = min(len(up_hits) * up_cfg.get("points_each", 0), up_cfg.get("cap", 0))
        down = min(len(down_hits) * down_cfg.get("points_each", 0), down_cfg.get("cap", 0))

        if up_hits:
            result.helps.append(_quoted(up_hits) + f" (+{up})")
        if down_hits:
            result.hurts.append(_quoted(down_hits) + f" → ICT risk (−{down})")

        points = max(0.0, min(float(max_points), base + up - down))
        result.likely_code = code
        result.confidence = confidence
        return Component("ANZSCO fit", points, max_points, basis)

    # -- sponsorship -------------------------------------------------------
    def _sponsorship(self, ad: Ad, result: Result) -> Component:
        cfg = self.config["sponsorship"]
        hits = find(ad.text, cfg.get("phrases", []))
        if hits:
            result.helps.append("sponsorship signal: " + _quoted(hits))
            return Component("Sponsorship signal", cfg["max_points"], cfg["max_points"], _quoted(hits))
        return Component("Sponsorship signal", 0.0, cfg["max_points"], "not mentioned (normal)")

    # -- salary ------------------------------------------------------------
    def _salary(self, ad: Ad, result: Result) -> Component:
        cfg = self.config["salary"]
        max_points = cfg["max_points"]
        amount = parse_salary(ad.description)
        if amount is None:
            result.unknowns.append("salary")
            question = self.config.get("questions", {}).get("salary_unknown")
            if question:
                result.questions.append(question)
            return Component("Salary", max_points / 2, max_points, "not stated — half points", True)

        for band in cfg.get("bands", []):
            if amount >= band["min"]:
                detail = f"${amount:,.0f} → {band['label']}"
                if band["points"] < max_points:
                    result.hurts.append(f"salary {detail}")
                return Component("Salary", float(band["points"]), max_points, detail)
        return Component("Salary", 0.0, max_points, f"${amount:,.0f}")

    # -- employment type ---------------------------------------------------
    def _employment(self, ad: Ad, result: Result) -> Component:
        cfg = self.config["employment_type"]
        max_points = cfg["max_points"]
        for kind in cfg.get("types", []):
            hits = find(ad.text, kind.get("phrases", []))
            if not hits:
                continue
            detail = f'{kind["label"]}: "{hits[0].quote}"'
            if kind.get("note"):
                result.unknowns.append(kind["note"])
                if kind["id"] == "part_time":
                    question = self.config.get("questions", {}).get("part_time_hours")
                    if question:
                        result.questions.append(question)
            if kind["points"] < max_points:
                result.hurts.append(f'employment type: {kind["label"]}')
            return Component("Employment type", float(kind["points"]), max_points, detail)

        result.unknowns.append("employment type")
        question = self.config.get("questions", {}).get("type_unknown")
        if question:
            result.questions.append(question)
        return Component("Employment type", max_points / 2, max_points, "not stated — half points", True)

    # -- entry point -------------------------------------------------------
    def score(self, ad: Ad) -> Result:
        result = Result(ad=ad)
        result.flags = self._flags(ad)
        result.knockouts = self._knockouts(ad)
        if result.knockouts:
            return result

        result.components = [
            self._anzsco(ad, result),
            self._sponsorship(ad, result),
            self._salary(ad, result),
            self._employment(ad, result),
        ]
        result.total = round(sum(c.points for c in result.components))
        return result


def _quoted(hits: list[Match]) -> str:
    return ", ".join(f'"{h.quote}"' for h in hits)


# --------------------------------------------------------------------------
# salary text -> a number
# --------------------------------------------------------------------------

_SALARY_PATTERNS = (
    re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+)"),          # $85,000
    re.compile(r"\$?\s?(\d{2,3})\s?k(?!\w)", re.I),    # $85k / 85k
    re.compile(r"\$\s?(\d{5,6})(?!\w)"),               # $85000
)

# An annual analyst salary. Anything outside this is an hourly rate, a day
# rate, a headcount or a dollar figure from the company blurb.
_SALARY_MIN, _SALARY_MAX = 30_000, 500_000


def parse_salary(text: str) -> float | None:
    """Midpoint of the salary range the ad states, or None if it states none."""
    values: set[float] = set()
    for pattern in _SALARY_PATTERNS:
        for raw in pattern.findall(text):
            value = float(raw.replace(",", ""))
            if value < 1000:      # came from the "k" pattern
                value *= 1000
            if _SALARY_MIN <= value <= _SALARY_MAX:
                values.add(value)
    if not values:
        return None
    return (min(values) + max(values)) / 2
