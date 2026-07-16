"""Shared 5-tier rating vocabulary and a deterministic heuristic parser.

The same five-tier scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager (investment plan recommendation)
- The Portfolio Manager (final position decision)
- The signal processor (rating extracted for downstream consumers)
- The memory log (rating tag stored alongside each decision entry)

Centralising it here avoids drift between those call sites.
"""

from __future__ import annotations

import re

# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)

_RATING_SET = {r.lower() for r in RATINGS_5_TIER}

# Matches "Rating: X" / "rating - X" / "Rating: **X**" — tolerates markdown
# bold wrappers and either a colon or hyphen separator.
_RATING_LABEL_RE = re.compile(
    r"^\s*\*{0,2}rating\*{0,2}\s*[:\-]\s*\*{0,2}(\w+)",
    re.IGNORECASE,
)


def extract_rating(text: str) -> str | None:
    """Extract an explicitly labelled or standalone 5-tier rating.

    Arbitrary prose is deliberately *not* scanned for the first rating word.  A
    sentence such as ``"not Buy; prefer Sell"`` must never be inverted to Buy
    merely because that token appeared first.  Structured output renders an
    explicit ``Rating: X`` label; conservative free-text fallbacks may return a
    single standalone rating line.
    """
    for line in text.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m and m.group(1).lower() in _RATING_SET:
            return m.group(1).capitalize()

    for line in text.splitlines():
        clean = line.strip().strip("*:.,").lower()
        if clean in _RATING_SET:
            return clean.capitalize()

    return None


def parse_rating(text: str, default: str = "Hold") -> str:
    """Return an explicit rating, or the fail-safe ``default`` (normally Hold)."""

    return extract_rating(text) or default
