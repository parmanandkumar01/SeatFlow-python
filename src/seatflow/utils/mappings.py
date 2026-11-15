"""Train class and quota label mappings.

Clean-room port of the two lookup tables embedded in the renderer bundle
``assets/utils-pOwDnddK.js``.  The original module keeps them as private
objects and exposes them through two accessor helpers; this module keeps the
same data and accessor names so the rest of the application has a single
source of truth.

The labels are the exact strings the original renderer displays, including
its abbreviations ("First AC", "SR. CITIZEN", "HANDICAPPED").
"""

from __future__ import annotations

from typing import Final

from .text import js_string, js_truthy

#: Booking class code -> human readable label (renderer ``a`` object).
TRAIN_CLASS_LABELS: Final[dict[str, str]] = {
    "2S": "Second Sitting (2S)",
    "SL": "Sleeper (SL)",
    "3A": "AC 3 Tier (3A)",
    "2A": "AC 2 Tier (2A)",
    "1A": "First AC (1A)",
    "CC": "Chair Car (CC)",
    "EC": "Executive Chair (EC)",
    "3E": "3rd AC Economy (3E)",
}

#: Quota code -> human readable label (renderer ``o`` object).
QUOTA_LABELS: Final[dict[str, str]] = {
    "GN": "GENERAL",
    "TQ": "TATKAL",
    "PT": "PREMIUM TATKAL",
    "LD": "LADIES",
    "SS": "SR. CITIZEN",
    "DP": "DUTY PASS",
    "HP": "HANDICAPPED",
}


def train_class_label(code: object) -> object:
    """Return the display label for a booking class code.

    Falsy codes yield ``""``.  Unknown codes are returned unchanged, mirroring
    the original ``code ? table[code] || code : ""`` fallback.
    """
    if not js_truthy(code):
        return ""
    key = code if isinstance(code, str) else js_string(code)
    return TRAIN_CLASS_LABELS.get(key, code)


def quota_label(code: object) -> object:
    """Return the display label for a quota code.

    Falsy codes yield ``""``.  Unknown codes are returned unchanged, mirroring
    the original ``code ? table[code] || code : ""`` fallback.
    """
    if not js_truthy(code):
        return ""
    key = code if isinstance(code, str) else js_string(code)
    return QUOTA_LABELS.get(key, code)