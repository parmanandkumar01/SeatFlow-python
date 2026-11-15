"""Manual 2FA / OTP entry dialog.

Displays a prompt for the user to enter the OTP/2FA code delivered
to their registered mobile/email. This dialog performs no automated
retrieval or transmission of the code; it only collects the typed
value and returns it to the caller.
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


class TwoFactorDialog(QDialog):
    """Modal dialog for manual OTP/2FA entry.

    Parameters
    ----------
    parent : QWidget | None
        Parent widget.
    prompt : str
        Optional descriptive prompt shown to the user.
    length : int
        Expected code length (hint only; not enforced strictly).
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        prompt: str = "Enter the OTP sent to your registered mobile/email:",
        length: int = 6,
    ) -> None:
        super().__init__(parent)
        self._length = length
        self.setWindowTitle("Two-Factor Authentication")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Two-Factor Authentication")
        header.setObjectName("dialog_header")
        layout.addWidget(header)

        prompt_label = QLabel(prompt)
        prompt_label.setWordWrap(True)
        layout.addWidget(prompt_label)

        form = QFormLayout()
        form.setSpacing(12)

        self.otp_edit = QLineEdit()
        self.otp_edit.setPlaceholderText(f"{length}-digit code")
        self.otp_edit.setMaxLength(length)
        self.otp_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        form.addRow("OTP*:", self.otp_edit)
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
        self.submit_button.setText("Verify")
        self.button_box.accepted.connect(self._on_submit)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _on_submit(self) -> None:
        """Validate and accept the entered OTP."""
        code = self.otp_edit.text().strip()
        if not code:
            self.error_label.setText("OTP code must not be empty.")
            self.error_label.show()
            return
        self.error_label.hide()
        self.accept()

    def get_otp_code(self) -> str:
        """Return the entered OTP code (stripped)."""
        return self.otp_edit.text().strip()