"""SVG watermark generator.

Clean-room port of the watermark helper in the renderer bundle
``assets/utils-pOwDnddK.js``.  The original renders a diagonal text label into
a data-URI that the UI applies as a repeating background on previews and
captured pages.

The produced value is a CSS ``url(...)`` token whose payload is a
percent-encoded ``data:image/svg+xml,<svg .../>`` document, so it can be dropped
straight into a stylesheet or a Qt resource.

Two details of the original are easy to miss and are reproduced here:

* the label is sanitised rather than escaped -- ``&``, ``<`` and ``>`` are
  replaced with spaces (the renderer cannot emit XML entities because the result
  is percent-encoded, not parsed as markup);
* a falsy label falls back to :data:`DEFAULT_TEXT`.
"""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import quote

from .text import js_number, js_string, js_truthy

#: Label used when the caller passes a falsy value.
DEFAULT_TEXT: Final[str] = "BINGO ORIGINAL"

#: Defaults used when the caller omits an option.
DEFAULT_WIDTH: Final[float] = 130
DEFAULT_HEIGHT: Final[float] = 62
DEFAULT_FONT_SIZE: Final[float] = 13
DEFAULT_LETTER_SPACING: Final[float] = 0.4

#: Rotation applied to the watermark text, in degrees.
ROTATION_DEGREES: Final[int] = -30

#: ``y`` position as a fraction of the height.
BASELINE_RATIO: Final[float] = 0.64

#: Characters the original replaces with a space before rendering.
_XML_UNSAFE_RE: Final[re.Pattern[str]] = re.compile(r"[<>&]")

#: ``encodeURIComponent`` leaves these characters unescaped.
_URI_SAFE: Final[str] = "!~*'()"

_SVG_TEMPLATE: Final[str] = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>"
    "<text x='{cx}' y='{baseline}' fill='#000' "
    "font-family='Inter,Arial,sans-serif' font-size='{font}' "
    "font-weight='800' letter-spacing='{spacing}' text-anchor='middle' "
    "transform='rotate({rotation} {cx} {cy})'>{text}</text></svg>"
)


def _sanitize_label(text: object) -> str:
    """Apply the original's label fallback and character replacement."""
    label = js_string(text) if js_truthy(text) else DEFAULT_TEXT
    return _XML_UNSAFE_RE.sub(" ", label).strip()


def svg_watermark(
    text: object,
    *,
    width: float = DEFAULT_WIDTH,
    height: float = DEFAULT_HEIGHT,
    font_size: float = DEFAULT_FONT_SIZE,
    letter_spacing: float = DEFAULT_LETTER_SPACING,
) -> str:
    """Return a CSS ``url(...)`` token containing an SVG watermark.

    ``width``/``height``/``font_size``/``letter_spacing`` correspond to the
    renderer's ``w``/``h``/``font``/``ls`` options and share its defaults.
    """
    cx = width / 2
    cy = height / 2
    baseline = f"{height * BASELINE_RATIO:.1f}"

    svg = _SVG_TEMPLATE.format(
        width=js_number(width),
        height=js_number(height),
        cx=js_number(cx),
        cy=js_number(cy),
        baseline=baseline,
        font=js_number(font_size),
        spacing=js_number(letter_spacing),
        rotation=ROTATION_DEGREES,
        text=_sanitize_label(text),
    )
    return f'url("data:image/svg+xml,{quote(svg, safe=_URI_SAFE)}")'