"""Application entry point.

Creates the QApplication, initializes the Application controller,
creates the main window, and starts the event loop.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from bingo_linux.app.application import Application
from bingo_linux.ui.theme import DARK_THEME_STYLE


def main() -> int:
    """Entry point for the Bingo Linux application.

    Returns:
        Application exit code.
    """
    app = QApplication(sys.argv)
    app.setApplicationName("Bingo Linux")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("Bingo Linux Project")
    app.setStyleSheet(DARK_THEME_STYLE)

    controller = Application()
    controller.create_main_window()
    return controller.run()


if __name__ == "__main__":
    sys.exit(main())
