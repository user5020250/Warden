"""
Parses short human-friendly duration strings such as "30s", "10m", "2hr",
"1d", or "permanent" into a number of seconds (or None for permanent).
Shared by every command that lets a moderator pick a custom duration
(/jail, /sentence, /visitation, /solitary, ...).
"""

import re

_UNIT_SECONDS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
}
_PERMANENT_WORDS = {"permanent", "perm", "forever"}
_PATTERN = re.compile(r"^(\d+)\s*([a-z]+)$")


def parse_duration(value: str, allow_permanent: bool = False) -> int | None:
    """
    Parses a duration string. Returns the duration in whole seconds, or
    None if the value means "permanent" (only accepted when
    allow_permanent is True). Raises ValueError with a user-friendly
    message if the string can't be parsed.
    """
    text = value.strip().lower()

    if text in _PERMANENT_WORDS:
        if not allow_permanent:
            raise ValueError("Permanent isn't a valid duration here.")
        return None

    match = _PATTERN.match(text)
    if not match or match.group(2) not in _UNIT_SECONDS:
        hint = " or 'permanent'" if allow_permanent else ""
        raise ValueError(
            f"Invalid duration '{value}'. Use a number followed by a unit "
            f"(e.g. 30s, 10m, 2hr, 1d){hint}."
        )

    amount, unit = match.groups()
    seconds = int(amount) * _UNIT_SECONDS[unit]
    if seconds <= 0:
        raise ValueError("Duration must be greater than zero.")
    return seconds
