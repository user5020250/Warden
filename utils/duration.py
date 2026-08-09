"""
Parses duration strings like "30s", "10m", "2hr", "1d" into seconds.
Also accepts "permanent" / "perm", which is represented as None throughout
the bot (no duration_seconds value = never auto-expires).
"""

import re

UNIT_SECONDS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
}

_PATTERN = re.compile(r"^\s*(\d+)\s*([a-zA-Z]+)\s*$")


def parse_duration(text: str) -> int | None:
    """Returns whole seconds, or None for a permanent duration. Raises
    ValueError with a user-facing message on anything unrecognized."""
    cleaned = text.strip().lower()
    if cleaned in ("permanent", "perm", "forever"):
        return None

    match = _PATTERN.match(cleaned)
    if not match:
        raise ValueError(
            f"`{text}` isn't a valid duration. Use a number plus a unit, e.g. `30s`, `10m`, `2hr`, `1d`, "
            "or `permanent`."
        )
    amount, unit = match.groups()
    if unit not in UNIT_SECONDS:
        raise ValueError(f"Unrecognized duration unit `{unit}`. Use `s`, `m`, `hr`, or `d`.")
    seconds = int(amount) * UNIT_SECONDS[unit]
    if seconds <= 0:
        raise ValueError("Duration must be greater than zero.")
    return seconds
