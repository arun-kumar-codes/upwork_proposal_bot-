"""Freelancer identity validation shared by import and proposal generation.

Blank-profile buckets and placeholder tokens ("Not named", "Unknown", "N/A")
are data artefacts, not people. They must never become selectable profiles
or sign a proposal. The Bot keeps the same list in bot/index.js.
"""

import re

_PLACEHOLDER_NAMES = {
    "",
    "-",
    "not",
    "not named",
    "unknown",
    "n/a",
    "na",
    "none",
    "null",
    "unnamed",
    "no name",
    "placeholder",
    "tbd",
    "anonymous",
    "not provided",
    "not specified",
    "missing",
}


def normalize_profile_name(raw: object) -> str:
    return re.sub(r"\s+", " ", str(raw or "").strip().lower())


def is_valid_profile_name(raw: object) -> bool:
    """True only for a plausible real freelancer name."""
    return normalize_profile_name(raw) not in _PLACEHOLDER_NAMES
