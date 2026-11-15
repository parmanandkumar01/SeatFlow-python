"""Theme configuration for SeatFlow (Dark Mode).

Matches the modern, high-contrast dark UI architecture inspired by Ocean
with rich obsidian/navy backgrounds, vivid purple brand accents, cyan highlights,
and high legibility.
"""

from __future__ import annotations

# Colors - Dark Mode
BG_ROOT = "#091a2b"
BG_SHELL = "#0a1e30"
BG_CARD = "#0c1e34"
BG_PANEL = "#0f2742"
BG_INPUT = "#081422"
BG_ROW_ALT = "#061222"
BG_HOVER = "#143048"

BORDER = "#134150"
BORDER_SOFT = "#1e3a5f"
BORDER_DARK = "#0e2d3e"
BORDER_FOCUS = "#7c3aed"

TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#e2e8f0"
TEXT_MUTED = "#94a3b8"
TEXT_CYAN = "#38bdf8"

BRAND_PURPLE = "#7c3aed"
BRAND_PURPLE_HOVER = "#8b5cf6"
BRAND_PURPLE_LIGHT = "#2e1065"
BRAND_PURPLE_BORDER = "#6d28d9"

ACCENT_CYAN = "#22d3ee"
ACCENT_CYAN_LIGHT = "#0c4a6e"

ACCENT_PINK = "#ec4899"
ACCENT_PINK_LIGHT = "#831843"

SUCCESS_GREEN = "#10b981"
SUCCESS_GREEN_LIGHT = "#064e3b"

DANGER_RED = "#ef4444"
DANGER_RED_LIGHT = "#450a0a"
DANGER_RED_HOVER = "#dc2626"

WARNING_ORANGE = "#f97316"
WARNING_ORANGE_LIGHT = "#7c2d12"

FONT_FAMILY = '"Segoe UI", "Inter", -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif'
FONT_MONO = '"Consolas", "Courier New", monospace'

# Global Dark Theme Stylesheet
DARK_THEME_STYLE = """
QWidget {
    font-family: "Segoe UI", "Inter", sans-serif;
    color: #e2e8f0;
    font-size: 13px;
}

QDialog, QMainWindow {
    background-color: #091a2b;
}

QLabel {
    color: #e2e8f0;
}

QLineEdit, QDateEdit, QComboBox, QTextEdit {
    background-color: #081422;
    color: #ffffff;
    border: 1px solid #1e3a5f;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: #7c3aed;
    selection-color: #ffffff;
}

QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid #7c3aed;
    background-color: #081422;
}

QLineEdit::placeholder {
    color: #64748b;
}

QComboBox::drop-down {
    border: none;
    padding-right: 6px;
}

QComboBox QAbstractItemView {
    background-color: #081422;
    color: #ffffff;
    border: 1px solid #1e3a5f;
    selection-background-color: #7c3aed;
    selection-color: #ffffff;
    padding: 4px;
}

QScrollBar:vertical {
    border: none;
    background: #081422;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #1e3a5f;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #7c3aed;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #081422;
    height: 8px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #1e3a5f;
    min-width: 20px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #7c3aed;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
"""
