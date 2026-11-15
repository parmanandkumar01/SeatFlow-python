"""Application entry point.

Creates the QApplication, initializes the Application controller,
creates the main window, and starts the event loop.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from seatflow.app.application import Application
from seatflow.ui.theme import DARK_THEME_STYLE


def main() -> int:
    """Entry point for the SeatFlow application.

    Returns:
        Application exit code.
    """
    app = QApplication(sys.argv)
    app.setApplicationName("SeatFlow")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("SeatFlow Project")
    app.setStyleSheet(DARK_THEME_STYLE)

    controller = Application()
    controller.create_main_window()
    return controller.run()


if __name__ == "__main__":
    sys.exit(main())
