"""Manual CAPTCHA entry dialog.

Displays a CAPTCHA challenge prompt and a single-line edit for the
user to type the code shown on the IRCTC page. This dialog performs
no image recognition or automated solving — the user reads and types
the CAPTCHA themselves.

The dialog does not load, store, or transmit the CAPTCHA text; it
returns the entered value to the caller via :class:`CaptchaDialog`.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class CaptchaDialog(QDialog):
    """Modal dialog for manual CAPTCHA entry.

    Parameters
    ----------
    parent : QWidget | None
        Parent widget.
    prompt : str
        Optional descriptive prompt (e.g., instructions). The CAPTCHA
        image itself is rendered by the browser; this dialog only
        collects the typed answer.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        prompt: str = "Enter the CAPTCHA code shown on the page:",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("CAPTCHA Verification")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Manual CAPTCHA Entry")
        header.setObjectName("dialog_header")
        layout.addWidget(header)

        prompt_label = QLabel(prompt)
        prompt_label.setWordWrap(True)
        layout.addWidget(prompt_label)

        form = QFormLayout()
        form.setSpacing(12)

        self.captcha_edit = QLineEdit()
        self.captcha_edit.setPlaceholderText("Type the characters you see")
        self.captcha_edit.setMaxLength(20)
        self.captcha_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        form.addRow("CAPTCHA*:", self.captcha_edit)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("dialog_error")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b00020;")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.submit_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Apply
        )
        self.submit_button.setText("Submit")
        self.button_box.accepted.connect(self._on_submit)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _on_submit(self) -> None:
        """Validate and accept the entered CAPTCHA."""
        text = self.captcha_edit.text().strip()
        if not text:
            self.error_label.setText("CAPTCHA code must not be empty.")
            self.error_label.show()
            return
        self.error_label.hide()
        self.accept()

    def get_captcha_text(self) -> str:
        """Return the entered CAPTCHA text (stripped)."""
        return self.captcha_edit.text().strip()