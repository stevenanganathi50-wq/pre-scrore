"""UTC time handling.

Every timestamp that crosses the database boundary uses one fixed-width UTC
format, so lexicographic comparison is chronological comparison. The
"prediction was made before kickoff" guarantee is enforced by a SQL trigger
comparing two of these strings, so the format is load-bearing, not cosmetic.
"""

from __future__ import annotations

from datetime import datetime, timezone

ISO_UTC = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime(ISO_UTC)


def now_iso() -> str:
    return to_iso(utc_now())


def parse_iso(value: str) -> datetime:
    """Parse our own format, and tolerate the common variants providers emit."""
    text = (value or "").strip()
    if not text:
        raise ValueError("empty timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def normalize(value: str) -> str:
    """Coerce any accepted timestamp spelling into our canonical format."""
    return to_iso(parse_iso(value))
