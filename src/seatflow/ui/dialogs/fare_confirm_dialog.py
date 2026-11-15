"""Fare change confirmation dialog.

Prompts the user to confirm or reject the fare presented by IRCTC
before proceeding to payment. This dialog performs no automated
acceptance; the user explicitly confirms or cancels.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class FareConfirmDialog(QDialog):
    """Modal dialog for manual fare confirmation.

    Parameters
    ----------
    parent : QWidget | None
        Parent widget.
    fare_amount : float | None
        The fare amount to confirm (display only).
    train_number : str | None
        Optional train number for context.
    journey_date : str | None
        Optional journey date for context.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        fare_amount: Optional[float] = None,
        train_number: Optional[str] = None,
        journey_date: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm Fare")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Confirm Fare")
        header.setObjectName("dialog_header")
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(12)

        if train_number:
            form.addRow("Train:", QLabel(str(train_number)))
        if journey_date:
            form.addRow("Journey Date:", QLabel(str(journey_date)))
        if fare_amount is not None:
            form.addRow("Fare:", QLabel(f"Rs. {fare_amount:,.2f}"))

        layout.addLayout(form)

        question = QLabel(
            "The fare above may have changed. Do you want to proceed "
            "with this fare?"
        )
        question.setWordWrap(True)
        layout.addWidget(question)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes
            | QDialogButtonBox.StandardButton.No
        )
        self.yes_button = self.button_box.button(QDialogButtonBox.StandardButton.Yes)
        self.yes_button.setText("Confirm")
        self.no_button = self.button_box.button(QDialogButtonBox.StandardButton.No)
        self.no_button.setText("Cancel")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def is_confirmed(self) -> bool:
        """Return True if the user confirmed the fare."""
        return self.result() == QDialog.DialogCode.Accepted.value