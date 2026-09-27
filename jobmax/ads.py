"""Reading job ads from disk.

An ad file is a small header, a line containing only `---`, then the ad text
exactly as it was copied from the job board:

    company: ELMO Software
    role: AI Analyst
    source: https://www.seek.com.au/job/12345678
    ---
    About the role
    ...

From Stage 2 the puller will build the same Ad objects straight from the API,
so the scorer never needs to know where an ad came from.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

SEPARATOR = "---"


@dataclass
class Ad:
    company: str
    role: str
    description: str
    source: str = ""
    location: str = ""
    path: Path | None = None
    extra: dict = field(default_factory=dict)

    @property
    def title(self) -> str:
        return f"{self.company} — {self.role}"

    @property
    def text(self) -> str:
        """Everything the scorer is allowed to read, header included.

        The role title matters (an "Engineer" ad is not an Org & Methods
        Analyst), so it is part of the searchable text.
        """
        return "\n".join([self.role, self.company, self.description])


class AdFormatError(ValueError):
    pass


def parse_ad(raw: str, path: Path | None = None) -> Ad:
    lines = raw.splitlines()
    try:
        cut = next(i for i, line in enumerate(lines) if line.strip() == SEPARATOR)
    except StopIteration:
        raise AdFormatError(
            f"{path or 'ad'}: no '---' line found. The file needs a "
            "'company:/role:' header, then a line with only --- , then the ad text."
        ) from None

    header = yaml.safe_load("\n".join(lines[:cut])) or {}
    if not isinstance(header, dict):
        raise AdFormatError(f"{path or 'ad'}: the header above --- is not 'key: value' lines.")

    header = {str(k).strip().lower(): v for k, v in header.items()}
    description = "\n".join(lines[cut + 1 :]).strip()

    missing = [k for k in ("company", "role") if not header.get(k)]
    if missing:
        raise AdFormatError(f"{path or 'ad'}: header is missing {', '.join(missing)}.")
    if not description:
        raise AdFormatError(f"{path or 'ad'}: there is no ad text below the --- line.")

    known = ("company", "role", "source", "location")
    return Ad(
        company=str(header["company"]).strip(),
        role=str(header["role"]).strip(),
        description=description,
        source=str(header.get("source") or "").strip(),
        location=str(header.get("location") or "").strip(),
        path=path,
        extra={k: v for k, v in header.items() if k not in known},
    )


def load_ad(path: Path) -> Ad:
    # utf-8-sig: Windows editors (Notepad, VS Code "UTF-8 with BOM") add a BOM
    # that would otherwise land inside the first header key.
    return parse_ad(path.read_text(encoding="utf-8-sig"), path=path)


def from_record(record: dict) -> Ad:
    """An Ad from a pulled job in data/jobs.json."""
    return Ad(
        company=record["company"],
        role=record["role"],
        description=record["description"],
        source=record.get("url", ""),
        location=record.get("location", ""),
        extra=record,
    )


def job_fact(description: str, label: str) -> str:
    """A value from the 'Job facts' block the puller writes at the top of an ad.

    Salary is tidied: LinkedIn writes "A$120,000.00/yr", this returns "$120,000".
    """
    for line in description.splitlines()[:8]:
        if line.startswith(label + ":"):
            value = line.split(":", 1)[1].strip()
            if label == "Salary":
                value = value.replace("A$", "$").replace(".00", "").replace("/yr", "")
            return value
    return ""


def load_dir(directory: Path) -> list[Ad]:
    paths = sorted(p for p in directory.glob("*.txt") if p.is_file())
    return [load_ad(p) for p in paths]
