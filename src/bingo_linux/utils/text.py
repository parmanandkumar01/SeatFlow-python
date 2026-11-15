"""Text helpers.

Clean-room port of the string helpers in the renderer bundle
``assets/utils-pOwDnddK.js``.

``gateway_slug(value)``
    Build the URL/file-system safe slug used when naming a captured payment
    gateway page.  The original upper-cases the label, drops a leading
    ``IRCTC`` token, and joins the remaining whitespace-separated tokens with
    ``-``.  It is intentionally lossy: ``"New Delhi - Mumbai Rajdhani"`` becomes
    ``"NEW-DELHI---MUMBAI-RAJDHANI"`` because the standalone dash survives as a
    token of its own.

``extract_train_number(value)``
    Pull the first standalone 4- or 5-digit train number out of a free-form
    string.  When no such number exists the trimmed string is returned so the
    caller can still show something meaningful.

The renderer relies on JavaScript's implicit ``String(...)`` coercion, so the
exact output for non-string inputs depends on it.  :func:`js_string` and
:func:`js_number` reproduce that coercion for the value shapes the UI can pass
(strings, numbers, booleans, arrays and plain objects).
"""

from __future__ import annotations

import re
from typing import Final

#: Leading ``IRCTC`` token, only when followed by whitespace.
_LEADING_IRCTC_RE: Final[re.Pattern[str]] = re.compile(r"^irctc\s+", re.IGNORECASE)

#: First standalone 4- or 5-digit run.
_TRAIN_NUMBER_RE: Final[re.Pattern[str]] = re.compile(r"\b(\d{4,5})\b")


def js_number(value: float) -> str:
    """Render a number the way JavaScript's ``String()`` would.

    Integral values lose the trailing ``.0``; everything else keeps the shortest
    round-trip representation, which matches V8 for the values used here.
    """
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return repr(float(value))


def js_string(value: object) -> str:
    """Reproduce JavaScript's ``String(value)`` coercion.

    ``None`` maps to ``""`` (the renderer never distinguishes ``null`` from an
    empty string here), booleans become ``true``/``false``, arrays join their
    stringified elements with commas, and plain objects become
    ``[object Object]``.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return js_number(value)
    if isinstance(value, dict):
        return "[object Object]"
    if isinstance(value, (list, tuple)):
        return ",".join(js_string(item) for item in value)
    return str(value)


def js_truthy(value: object) -> bool:
    """Reproduce JavaScript's notion of truthiness.

    ``false``, ``0``, ``-0``, ``NaN``, ``""``, ``null`` and ``undefined`` are
    falsy; every other value -- including empty arrays and objects -- is truthy.
    """
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value != ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and value != value:  # NaN
            return False
        return value != 0
    return True


def gateway_slug(value: object) -> str:
    """Return the upper-case, dash-joined slug for a gateway label.

    Falsy values produce ``""``; truthy values are stringified with JavaScript
    semantics before the leading ``IRCTC`` token is dropped.
    """
    text = js_string(value) if js_truthy(value) else ""
    text = text.strip()
    text = _LEADING_IRCTC_RE.sub("", text)
    tokens = [token for token in re.split(r"\s+", text) if token]
    return "-".join(token.upper() for token in tokens)


def extract_train_number(value: object) -> object:
    """Return the first standalone 4- or 5-digit number in ``value``.

    Falsy values return ``None``.  Anything else is stringified, and when no
    number is present the trimmed string is returned.
    """
    if not js_truthy(value):
        return None
    text = js_string(value)
    match = _TRAIN_NUMBER_RE.search(text)
    if match is not None:
        return match.group(1)
    return text.strip()