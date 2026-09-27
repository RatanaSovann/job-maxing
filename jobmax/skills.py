"""Skills fit: how much of what an ad asks for I can show proof of.

Kept apart from the goal rubric on purpose. The PR score answers "is this job
good for my goal"; this answers "do I have what they ask for". Both are shown,
neither changes the other.

The profile (profile/skills.yaml) holds the skills, how ads word them, my
level in each, and the evidence. Nothing here is specific to one person.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .ads import Ad
from .scorer import find


@dataclass(frozen=True)
class SkillHit:
    name: str       # from the profile, e.g. "SQL"
    quote: str      # what the ad actually says
    evidence: str   # my proof, from the profile ("" if none)

    def __str__(self) -> str:
        line = f'{self.name} "{self.quote}"'
        return f"{line} ({self.evidence})" if self.evidence else line


@dataclass
class SkillFit:
    score: int | None = None                                # None: the ad names none of my listed skills
    have: list[SkillHit] = field(default_factory=list)
    partial: list[SkillHit] = field(default_factory=list)
    missing: list[SkillHit] = field(default_factory=list)


class SkillProfile:
    def __init__(self, config: dict):
        self.levels: dict[str, float] = config["levels"]
        self.skills: list[dict] = config.get("skills", [])
        for skill in self.skills:
            if skill.get("level") not in self.levels:
                raise ValueError(f'skill "{skill.get("name")}": level must be one of '
                                 f'{", ".join(self.levels)}, got {skill.get("level")!r}')

    @classmethod
    def load(cls, path: Path) -> "SkillProfile":
        return cls(yaml.safe_load(path.read_text(encoding="utf-8-sig")))

    def match(self, ad: Ad) -> SkillFit:
        """Score = average of my level across the skills the ad asks for, out of 100."""
        fit = SkillFit()
        earned = 0.0
        asked = 0
        for skill in self.skills:
            hits = find(ad.text, skill.get("phrases", []))
            if not hits:
                continue
            asked += 1
            weight = self.levels[skill["level"]]
            earned += weight
            line = SkillHit(skill["name"], hits[0].quote, skill.get("evidence", ""))
            if weight >= 1:
                fit.have.append(line)
            elif weight > 0:
                fit.partial.append(line)
            else:
                fit.missing.append(line)
        if asked:
            fit.score = round(100 * earned / asked)
        return fit
