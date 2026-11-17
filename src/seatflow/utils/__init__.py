"""Shared, dependency-free helpers.

The modules in this package are clean-room ports of the renderer bundle
``assets/utils-pOwDnddK.js``.  Every helper is pure: no Qt, no database, no
network access, so they can be reused from both the UI and the service layer.
"""

from __future__ import annotations

from .dates import (
    display_to_iso,
    iso_to_display,
    tatkal_adjust,
    today_utc,
    tomorrow_utc,
)
from .mappings import (
    QUOTA_LABELS,
    TRAIN_CLASS_LABELS,
    quota_label,
    train_class_label,
)
from .resources import (
    get_asset_path,
    get_bundle_dir,
    get_data_dir,
    get_resource_path,
)
from .text import extract_train_number, gateway_slug, js_number, js_string, js_truthy
from .watermark import (
    DEFAULT_FONT_SIZE,
    DEFAULT_HEIGHT,
    DEFAULT_LETTER_SPACING,
    DEFAULT_TEXT,
    DEFAULT_WIDTH,
    svg_watermark,
)

__all__ = [
    "DEFAULT_FONT_SIZE",
    "DEFAULT_HEIGHT",
    "DEFAULT_LETTER_SPACING",
    "DEFAULT_TEXT",
    "DEFAULT_WIDTH",
    "QUOTA_LABELS",
    "TRAIN_CLASS_LABELS",
    "display_to_iso",
    "extract_train_number",
    "gateway_slug",
    "get_asset_path",
    "get_bundle_dir",
    "get_data_dir",
    "get_resource_path",
    "iso_to_display",
    "js_number",
    "js_string",
    "js_truthy",
    "quota_label",
    "svg_watermark",
    "tatkal_adjust",
    "today_utc",
    "tomorrow_utc",
    "train_class_label",
]
