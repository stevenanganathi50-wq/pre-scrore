"""Configuration read from the environment, with a .env fallback.

Secrets live in .env (gitignored) or in real environment variables. Nothing
here ever logs a key value -- `describe()` exists so a human can confirm what
is loaded without the secret appearing in terminal output or a CI log.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import config

ENV_PATH = config.ROOT / ".env"


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """Parse a .env file. Real environment variables win over the file."""
    target = path or ENV_PATH
    values: dict[str, str] = {}
    if not target.exists():
        return values

    # utf-8-sig: PowerShell's Set-Content -Encoding utf8 writes a BOM on
    # Windows PowerShell 5.1, which would otherwise corrupt the first key name.
    for line in target.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value:
            values[key.strip()] = value
    return values


def get(name: str, default: str | None = None) -> str | None:
    if name in os.environ and os.environ[name]:
        return os.environ[name]
    return load_env_file().get(name, default)


@dataclass(frozen=True)
class SupabaseSettings:
    url: str
    service_role_key: str
    anon_key: str | None = None

    @property
    def rest_url(self) -> str:
        return f"{self.url.rstrip('/')}/rest/v1"


class MissingSettings(RuntimeError):
    pass


def supabase(require_service_role: bool = True) -> SupabaseSettings:
    url = get("SUPABASE_URL")
    service = get("SUPABASE_SERVICE_ROLE_KEY")
    anon = get("SUPABASE_ANON_KEY")

    missing = [n for n, v in (("SUPABASE_URL", url),) if not v]
    if require_service_role and not service:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise MissingSettings(
            "missing "
            + ", ".join(missing)
            + f"\n\nCopy .env.example to .env and fill it in:\n  {ENV_PATH}"
        )

    return SupabaseSettings(url=url, service_role_key=service or "", anon_key=anon)


def describe() -> str:
    """Human-readable status with no secret values in it."""
    def state(name: str) -> str:
        value = get(name)
        if not value:
            return "MISSING"
        return f"set ({len(value)} chars)"

    return "\n".join(
        [
            f"SUPABASE_URL               {get('SUPABASE_URL') or 'MISSING'}",
            f"SUPABASE_ANON_KEY          {state('SUPABASE_ANON_KEY')}",
            f"SUPABASE_SERVICE_ROLE_KEY  {state('SUPABASE_SERVICE_ROLE_KEY')}",
            f"API_FOOTBALL_KEY           {state('API_FOOTBALL_KEY')}",
            f"source                     {ENV_PATH if ENV_PATH.exists() else 'environment only'}",
        ]
    )
