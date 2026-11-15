"""Cross-platform window drag support for frameless windows.

Supports Linux Wayland (startSystemMove) and X11 / compositors.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QScrollBar,
    QSlider,
    QSpinBox,
    QTabBar,
    QTextEdit,
    QWidget,
)

INTERACTIVE_WIDGET_TYPES = (
    QAbstractButton,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QAbstractItemView,
    QComboBox,
    QSpinBox,
    QSlider,
    QTabBar,
    QScrollBar,
)


def start_window_drag(window: QWidget, event) -> bool:
    """Initiates native system move on Wayland / modern desktop compositors."""
    if event.button() == Qt.MouseButton.LeftButton:
        target_win = window.window()
        handle = target_win.windowHandle()
        if handle and hasattr(handle, "startSystemMove"):
            try:
                if handle.startSystemMove():
                    return True
            except Exception:
                pass
    return False


class WindowDragFilter(QObject):
    """Drag filter installed on windows or header handles."""

    def __init__(self, window: QWidget, *handles: QWidget | None):
        super().__init__(window)
        self.window = window
        self._drag_pos: QPoint | None = None
        self._handles: list[QWidget] = []
        for h in handles:
            if h is not None:
                self.add_handle(h)

    def add_handle(self, handle: QWidget) -> None:
        if handle not in self._handles:
            self._handles.append(handle)
            handle.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                child = watched.childAt(pos) if isinstance(watched, QWidget) else None
                if child and isinstance(child, INTERACTIVE_WIDGET_TYPES):
                    return False
                if start_window_drag(self.window, event):
                    return True
                self._drag_pos = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
                return True
        elif event.type() == QEvent.Type.MouseMove:
            if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
                self.window.move(event.globalPosition().toPoint() - self._drag_pos)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = None
                return True
        return False


def enable_window_drag(window: QWidget, *handles: QWidget | None) -> WindowDragFilter:
    """Convenience helper to enable smooth dragging on a window."""
    filter_ = WindowDragFilter(window, *handles)
    window.installEventFilter(filter_)
    return filter_
