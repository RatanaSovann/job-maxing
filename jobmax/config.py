"""Reads .env. Secrets live there and nowhere else."""

from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent


class MissingSecret(RuntimeError):
    pass


def secret(name: str) -> str:
    value = (dotenv_values(ROOT / ".env") or {}).get(name) or ""
    value = value.strip().strip('"').strip("'")
    if not value:
        raise MissingSecret(
            f"{name} is empty or missing in {ROOT / '.env'}.\n"
            f"Copy .env.example to .env and fill it in (no quotes, no spaces around '=')."
        )
    return value
