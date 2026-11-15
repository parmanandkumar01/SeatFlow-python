"""Date and time helpers.

Clean-room port of the date/time subset of the renderer bundle
``assets/utils-pOwDnddK.js``.  The original helpers are deliberately lenient
about their inputs and are used to pre-fill journey dates and to normalise
values coming from the UI, so the exact acceptance rules matter.

Behaviour reproduced here:

``today_utc()``
    Current UTC calendar day as ``YYYY-MM-DD`` (the original slices
    ``new Date().toISOString()``).

``tomorrow_utc()``
    Current UTC calendar day plus one day, same format.

``iso_to_display(value)``
    Convert a leading ``YYYY-MM-DD`` prefix to ``DD-MM-YYYY``.  The match is a
    *prefix* match, so timestamps such as ``2026-11-15T10:30:00Z`` are
    accepted.  Anything that does not start with a four/two/two digit date is
    returned unchanged.

``display_to_iso(value)``
    Convert an exact ``DD-MM-YYYY`` string to ``YYYY-MM-DD``.  The match is
    anchored at both ends, so trailing whitespace or a time component makes the
    conversion fail and an empty string is returned.

``tatkal_adjust(value)``
    Correct a timestamp captured inside the Tatkal booking window.  The
    original shifts the clock back by a small, minute-dependent offset during
    the 10:00 (AC) and 11:00 (non-AC) opening minutes.  Non-datetime values and
    timestamps outside those hours are returned unchanged.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Final

from .text import js_truthy

#: ``YYYY-MM-DD`` prefix accepted by :func:`iso_to_display`.
_ISO_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")

#: ``YYYY-MM-DD`` exact match already in ISO form.
_ISO_FULL_RE: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: ``DD-MM-YYYY`` full match accepted by :func:`display_to_iso`.
_DISPLAY_FULL_RE: Final[re.Pattern[str]] = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")

#: Tatkal opening hours, in local time, as used by the original renderer.
_TATKAL_HOURS = (10, 11)

#: Fixed back-shift applied from the second minute of the window onwards.
_TATKAL_LATE_OFFSET_SECONDS = 40

#: Cap applied during the first minute of the window.
_TATKAL_FIRST_MINUTE_CAP_SECONDS = 30


def today_utc() -> str:
    """Return the current UTC date as ``YYYY-MM-DD``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def tomorrow_utc() -> str:
    """Return the current UTC date plus one day as ``YYYY-MM-DD``."""
    return (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")


def iso_to_display(value: object) -> object:
    """Convert a leading ``YYYY-MM-DD`` to ``DD-MM-YYYY``.

    Falsy values become ``""``.  Strings without a leading ISO date, and any
    truthy non-string value, are returned unchanged -- the original relies on
    the regex coercing its argument and falling through to the input.
    """
    if not js_truthy(value):
        return ""
    if not isinstance(value, str):
        return value
    match = _ISO_PREFIX_RE.match(value)
    if match is None:
        return value
    year, month, day = match.groups()
    return f"{day}-{month}-{year}"


def display_to_iso(value: object) -> str:
    """Convert an exact ``DD-MM-YYYY`` string to ``YYYY-MM-DD``.

    Values already in exact ``YYYY-MM-DD`` form are returned unchanged.  Anything
    else that is not an exact ``DD-MM-YYYY`` match -- including trailing
    whitespace and a time component -- yields ``""``.
    """
    if not js_truthy(value):
        return ""
    if not isinstance(value, str):
        return ""
    if _ISO_FULL_RE.match(value):
        return value
    match = _DISPLAY_FULL_RE.match(value)
    if match is None:
        return ""
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def tatkal_adjust(value: object) -> object:
    """Shift a timestamp captured inside the Tatkal opening window.

    ``datetime`` values observed at 10:xx or 11:xx local time are moved back by
    a small offset:

    * minute ``0`` -> unchanged;
    * minute ``1`` -> back by ``min(second + 1, 30)`` seconds;
    * minute ``2`` and above -> back by ``40`` seconds.

    Everything else, including non-``datetime`` values, is returned unchanged.
    """
    if not isinstance(value, datetime):
        return value
    if value.hour not in _TATKAL_HOURS:
        return value
    if value.minute == 0:
        return value
    if value.minute == 1:
        offset = min(value.second + 1, _TATKAL_FIRST_MINUTE_CAP_SECONDS)
    else:
        offset = _TATKAL_LATE_OFFSET_SECONDS
    return value - timedelta(seconds=offset)