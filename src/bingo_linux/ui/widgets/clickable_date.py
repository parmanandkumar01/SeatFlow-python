"""Clickable date edit with popup calendar styled for light theme."""

from __future__ import annotations

from PySide6.QtCore import QDate, QEvent, QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCalendarWidget,
    QDateEdit,
    QWidget,
)


class ClickableDateEdit(QDateEdit):
    """DateEdit with a custom popup calendar that uses clean light theme styling."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCalendarPopup(False)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setDisplayFormat("dd-MMM-yyyy")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.lineEdit().installEventFilter(self)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setStyleSheet(
            "background: transparent; color: #ffffff; border: none; font-size: 13px; font-weight: 600;"
        )

        # Standalone popup calendar
        self._cal = QCalendarWidget()
        self._cal.setWindowFlags(Qt.WindowType.Popup)
        self._cal.setFixedSize(260, 220)
        self._cal.clicked.connect(self._on_cal_clicked)
        self._style_calendar()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.lineEdit() and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._toggle_calendar()
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_calendar()
        else:
            super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        w = max(10, self.width() - 20)
        h = max(10, self.height() - 8)
        self.lineEdit().setGeometry(10, 4, w, h)

    def _toggle_calendar(self) -> None:
        if self._cal.isVisible():
            self._cal.hide()
        else:
            self._cal.setSelectedDate(self.date())
            pos = self.lineEdit().mapToGlobal(QPoint(0, self.lineEdit().height() + 4))
            self._cal.move(pos)
            self._cal.show()
            self._cal.raise_()
            self._cal.activateWindow()

    def _on_cal_clicked(self, qdate: QDate) -> None:
        self.setDate(qdate)
        self._cal.hide()

    def _style_calendar(self) -> None:
        self._cal.setStyleSheet("""
            QCalendarWidget {
                background-color: #081422;
                border: 1px solid #1e3a5f;
                border-radius: 8px;
            }
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background-color: #0c1e34;
                border-bottom: 1px solid #1e3a5f;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                min-height: 36px;
            }
            QCalendarWidget QToolButton {
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QCalendarWidget QToolButton:hover {
                background-color: #143048;
                color: #38bdf8;
            }
            QCalendarWidget QTableView {
                background-color: #081422;
                alternate-background-color: #061222;
                selection-background-color: #7c3aed;
                selection-color: #ffffff;
                color: #ffffff;
                gridline-color: #0e2d3e;
            }
            QCalendarWidget QMenu {
                background-color: #081422;
                color: #ffffff;
                border: 1px solid #1e3a5f;
            }
            QCalendarWidget QSpinBox {
                background-color: #0c1e34;
                color: #ffffff;
                border: 1px solid #1e3a5f;
                border-radius: 4px;
            }
        """)
