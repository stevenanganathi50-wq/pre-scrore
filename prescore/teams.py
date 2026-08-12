"""Team name resolution across data sources.

Our canonical names are football-data.co.uk's, because that is where the
history — and therefore every rating — comes from. Every other source has to
be mapped onto them.

The rule that matters: an unrecognised name is never silently turned into a
new team. Doing that once already corrupted the ratings (see the Div=EC
incident in the README), and it fails quietly, which is the worst way to fail.
Unknown names are reported and the caller decides.
"""

from __future__ import annotations

import re
import sqlite3

from . import store

# Provider spelling -> our canonical spelling. Only entries that actually
# differ need to be here; identical names resolve on their own.
ALIASES: dict[str, str] = {
    # TheSportsDB spellings
    "AFC Bournemouth": "Bournemouth",
    "Brighton and Hove Albion": "Brighton",
    "Brighton & Hove Albion": "Brighton",
    "Cardiff City": "Cardiff",
    "Coventry City": "Coventry",
    "Huddersfield Town": "Huddersfield",
    "Hull City": "Hull",
    "Ipswich Town": "Ipswich",
    "Leeds United": "Leeds",
    "Leicester City": "Leicester",
    "Luton Town": "Luton",
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Newcastle United": "Newcastle",
    "Norwich City": "Norwich",
    "Nottingham Forest": "Nott'm Forest",
    "Nott'ham Forest": "Nott'm Forest",
    "Sheffield Utd": "Sheffield United",
    "Stoke City": "Stoke",
    "Swansea City": "Swansea",
    "Tottenham Hotspur": "Tottenham",
    "West Bromwich Albion": "West Brom",
    "West Ham United": "West Ham",
    "Wolverhampton Wanderers": "Wolves",
    "Wolverhampton": "Wolves",
}

_SUFFIXES = re.compile(r"\s+(FC|AFC|CF)$", re.IGNORECASE)


def _tidy(name: str) -> str:
    name = (name or "").strip()
    name = _SUFFIXES.sub("", name)
    return re.sub(r"\s+", " ", name)


def resolve(conn: sqlite3.Connection, name: str, source: str) -> str | None:
    """Map a provider's team name onto our canonical name.

    Resolution order: recorded alias, explicit alias table, exact canonical
    match, then a tidied case-insensitive match. Returns None if none hit --
    deliberately, so callers surface the gap instead of inventing a team.
    """
    tidied = _tidy(name)
    if not tidied:
        return None

    team_id = store.resolve_alias(conn, name, source)
    if team_id is not None:
        row = conn.execute("SELECT name FROM teams WHERE id = ?", (team_id,)).fetchone()
        if row:
            return row["name"]

    if tidied in ALIASES:
        return ALIASES[tidied]

    row = conn.execute("SELECT name FROM teams WHERE name = ?", (tidied,)).fetchone()
    if row:
        return row["name"]

    row = conn.execute(
        "SELECT name FROM teams WHERE lower(name) = lower(?)", (tidied,)
    ).fetchone()
    if row:
        return row["name"]

    return None


def resolve_all(
    conn: sqlite3.Connection, names: list[str], source: str
) -> tuple[dict[str, str], list[str]]:
    """Resolve many names at once. Returns (resolved, unresolved)."""
    resolved: dict[str, str] = {}
    unresolved: list[str] = []
    for name in names:
        canonical = resolve(conn, name, source)
        if canonical is None:
            unresolved.append(name)
        else:
            resolved[name] = canonical
    return resolved, sorted(set(unresolved))


def register(conn: sqlite3.Connection, name: str, source: str, canonical: str) -> int:
    """Record that `name` from `source` means `canonical`, creating the team."""
    tid = store.team_id(conn, canonical)
    store.add_alias(conn, name, source, tid)
    return tid
