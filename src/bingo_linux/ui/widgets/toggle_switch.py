"""ToggleSwitch and YesNoToggle widgets matching the official UI."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class ToggleSwitch(QWidget):
    """Modern iOS/Fluent-style toggle switch for boolean settings."""
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(42, 22)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, val: bool) -> None:
        if self._checked != val:
            self._checked = val
            self.update()
            self.toggled.emit(val)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
            event.accept()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        # Track
        track_color = QColor("#7c3aed") if self._checked else QColor("#1e293b")
        border_color = QColor("#8b5cf6") if self._checked else QColor("#334155")
        p.setBrush(QBrush(track_color))
        p.setPen(QPen(border_color, 1))
        p.drawRoundedRect(1, 1, w - 2, h - 2, (h - 2) / 2, (h - 2) / 2)

        # Thumb
        thumb_diam = h - 6
        thumb_x = (w - thumb_diam - 3) if self._checked else 3
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(thumb_x), 3, int(thumb_diam), int(thumb_diam))
        p.end()


class YesNoToggle(QWidget):
    """YES / NO pill toggle matching the official UI."""
    toggled = Signal(bool)  # True = YES, False = NO

    def __init__(self, initial_yes: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._yes = initial_yes
        self.setFixedSize(76, 26)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def is_yes(self) -> bool:
        return self._yes

    def isChecked(self) -> bool:
        return self._yes

    def set_yes(self, val: bool) -> None:
        if self._yes != val:
            self._yes = val
            self.update()
            self.toggled.emit(val)

    def setChecked(self, val: bool) -> None:
        self.set_yes(val)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            click_x = event.position().x()
            if click_x < self.width() / 2:
                self.set_yes(True)
            else:
                self.set_yes(False)
            event.accept()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        # Background track
        p.setBrush(QBrush(QColor("#081422")))
        p.setPen(QPen(QColor("#1e3a5f"), 1))
        p.drawRoundedRect(1, 1, w - 2, h - 2, (h - 2) / 2, (h - 2) / 2)

        # Active thumb
        half_w = (w - 4) / 2
        thumb_x = 2 if self._yes else (2 + half_w)
        thumb_color = QColor("#0ea5e9") if self._yes else QColor("#7c3aed")
        p.setBrush(QBrush(thumb_color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(int(thumb_x), 2, int(half_w), h - 4, (h - 4) / 2, (h - 4) / 2)

        # Text labels
        f = p.font()
        f.setPointSize(8)
        f.setBold(True)
        p.setFont(f)

        # YES label
        p.setPen(QColor("#ffffff") if self._yes else QColor("#94a3b8"))
        p.drawText(2, 2, int(half_w), h - 4, Qt.AlignmentFlag.AlignCenter, "YES")

        # NO label
        p.setPen(QColor("#ffffff") if not self._yes else QColor("#94a3b8"))
        p.drawText(int(2 + half_w), 2, int(half_w), h - 4, Qt.AlignmentFlag.AlignCenter, "NO")
        p.end()
