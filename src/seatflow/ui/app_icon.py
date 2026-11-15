"""Application icon and branding helpers for SeatFlow."""

from __future__ import annotations

import os
from pathlib import Path
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QWidget

_CACHED_ICON: QIcon | None = None
_CACHED_PIXMAP: QPixmap | None = None


def get_logo_path() -> str:
    """Return absolute path to SeatFlow logo PNG."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "assets" / "logo.png",
        Path.cwd() / "assets" / "logo.png",
        Path.cwd() / "SeatFlow" / "assets" / "logo.png",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return ""


def bingo_icon() -> QIcon:
    """Return QIcon of SeatFlow logo."""
    global _CACHED_ICON
    if _CACHED_ICON is None:
        p = get_logo_path()
        if p and os.path.exists(p):
            _CACHED_ICON = QIcon(p)
        else:
            _CACHED_ICON = QIcon()
    return _CACHED_ICON


def bingo_logo_pixmap(size: int = 28) -> QPixmap:
    """Return scaled QPixmap of SeatFlow logo."""
    global _CACHED_PIXMAP
    p = get_logo_path()
    if p and os.path.exists(p):
        pm = QPixmap(p)
        return pm.scaled(size, size)
    pm = QPixmap(size, size)
    pm.fill()
    return pm


def apply_bingo_icon(window: QWidget) -> None:
    """Apply SeatFlow icon to window."""
    window.setWindowIcon(bingo_icon())


seatflow_icon = bingo_icon
apply_seatflow_icon = apply_bingo_icon
seatflow_logo_pixmap = bingo_logo_pixmap

