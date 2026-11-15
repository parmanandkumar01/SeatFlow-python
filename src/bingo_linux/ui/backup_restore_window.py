"""Backup and restore window for Bingo Linux."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bingo_linux.ui.app_icon import apply_bingo_icon
from bingo_linux.ui.window_drag import enable_window_drag


class BackupRestoreWindow(QWidget):
    """Encrypted data backup & restore window."""

    export_requested = Signal(str, str)          # file_path, password
    import_requested = Signal(str, str, str)     # file_path, password, mode ('merge'/'replace')

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_bingo_icon(self)
        self.setWindowTitle("Backup & Restore")
        self.setFixedSize(540, 480)
        self.setObjectName("backupWindowRoot")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self._setup_ui()
        self._setup_styles()
        enable_window_drag(self, self.head_frame)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        main_card = QFrame()
        main_card.setObjectName("bakMainCard")
        lay = QVBoxLayout(main_card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        self.head_frame = QFrame()
        self.head_frame.setObjectName("bakHead")
        self.head_frame.setFixedHeight(54)
        hl = QHBoxLayout(self.head_frame)
        hl.setContentsMargins(18, 10, 14, 10)
        hl.setSpacing(12)

        icon_lbl = QLabel("💾")
        icon_lbl.setStyleSheet("font-size: 18px;")
        hl.addWidget(icon_lbl)

        title_lbl = QLabel("BACKUP & RESTORE (.bingo)")
        title_lbl.setObjectName("bakTitle")
        hl.addWidget(title_lbl)

        hl.addStretch(1)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("bakClose")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.clicked.connect(self.hide)
        hl.addWidget(self.btn_close)

        lay.addWidget(self.head_frame)

        # Body
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 20, 24, 20)
        bl.setSpacing(18)

        # 1. Export Card
        exp_card = QFrame()
        exp_card.setObjectName("sectionCard")
        el = QVBoxLayout(exp_card)
        el.setContentsMargins(16, 14, 16, 14)
        el.setSpacing(10)

        exp_title = QLabel("EXPORT ENCRYPTED BACKUP")
        exp_title.setObjectName("sectionTitle")
        el.addWidget(exp_title)

        self.exp_pass = QLineEdit()
        self.exp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.exp_pass.setPlaceholderText("Enter a password to encrypt your backup...")
        self.exp_pass.setFixedHeight(36)
        el.addWidget(self.exp_pass)

        self.btn_export = QPushButton("📤  Export .bingo File")
        self.btn_export.setObjectName("btnPurplePrimary")
        self.btn_export.setFixedHeight(36)
        self.btn_export.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_export.clicked.connect(self._on_export)
        el.addWidget(self.btn_export)

        bl.addWidget(exp_card)

        # 2. Import Card
        imp_card = QFrame()
        imp_card.setObjectName("sectionCard")
        il = QVBoxLayout(imp_card)
        il.setContentsMargins(16, 14, 16, 14)
        il.setSpacing(10)

        imp_title = QLabel("RESTORE BACKUP")
        imp_title.setObjectName("sectionTitle")
        il.addWidget(imp_title)

        f_row = QHBoxLayout()
        f_row.setSpacing(6)
        self.imp_file_edit = QLineEdit()
        self.imp_file_edit.setPlaceholderText("Select .bingo file...")
        self.imp_file_edit.setFixedHeight(36)
        f_row.addWidget(self.imp_file_edit)

        self.btn_browse = QPushButton("Browse")
        self.btn_browse.setObjectName("btnSecondary")
        self.btn_browse.setFixedHeight(36)
        self.btn_browse.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_browse.clicked.connect(self._browse_import_file)
        f_row.addWidget(self.btn_browse)
        il.addLayout(f_row)

        self.imp_pass = QLineEdit()
        self.imp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.imp_pass.setPlaceholderText("Enter the backup password...")
        self.imp_pass.setFixedHeight(36)
        il.addWidget(self.imp_pass)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        m_lbl = QLabel("Import Mode:")
        m_lbl.setStyleSheet("font-weight: 600; color: #94a3b8;")
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Merge (Keep existing & add new)", "merge")
        self.mode_combo.addItem("Replace (Wipe existing & restore)", "replace")
        self.mode_combo.setFixedHeight(34)
        mode_row.addWidget(m_lbl)
        mode_row.addWidget(self.mode_combo, 1)
        il.addLayout(mode_row)

        self.btn_import = QPushButton("📥  Restore Now")
        self.btn_import.setObjectName("btnPurplePrimary")
        self.btn_import.setFixedHeight(36)
        self.btn_import.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_import.clicked.connect(self._on_import)
        il.addWidget(self.btn_import)

        bl.addWidget(imp_card)
        bl.addStretch(1)

        lay.addWidget(body)
        root.addWidget(main_card)

    def _setup_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#backupWindowRoot {
                background: transparent;
            }
            QFrame#bakMainCard {
                background: #091a2b;
                border: 1px solid #1e3a5f;
                border-radius: 12px;
            }
            QFrame#bakHead {
                background: #0c1e34;
                border-bottom: 1px solid #1e3a5f;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#bakTitle {
                color: #ffffff;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QPushButton#bakClose {
                background: #0d1a28;
                color: #e8f4fa;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#bakClose:hover {
                background: #dc2626;
                border-color: #ef4444;
                color: #ffffff;
            }
            QFrame#sectionCard {
                background: #0c1e34;
                border: 1px solid #1e3a5f;
                border-radius: 8px;
            }
            QLabel#sectionTitle {
                font-size: 11px;
                font-weight: 800;
                color: #38bdf8;
                letter-spacing: 0.5px;
            }
            QLineEdit {
                background: #081422;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                color: #ffffff;
                padding: 4px 8px;
            }
            QLineEdit:focus {
                border-color: #7c3aed;
            }
            QComboBox {
                background: #081422;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                color: #ffffff;
                padding: 4px 8px;
            }
            QComboBox QAbstractItemView {
                background: #081422;
                color: #ffffff;
                border: 1px solid #1e3a5f;
                selection-background-color: #7c3aed;
                selection-color: #ffffff;
            }
            QPushButton#btnPurplePrimary {
                background: #7c3aed;
                color: #ffffff;
                border: 1px solid #6d28d9;
                border-radius: 6px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton#btnPurplePrimary:hover {
                background: #8b5cf6;
            }
            QPushButton#btnSecondary {
                background: #0d2238;
                color: #38bdf8;
                border: 1px solid #1e3a5f;
                border-radius: 6px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton#btnSecondary:hover {
                background: #143048;
                border-color: #38bdf8;
            }
        """)

    def _on_export(self) -> None:
        pwd = self.exp_pass.text()
        if not pwd:
            QMessageBox.warning(self, "Password Required", "Please enter a password to encrypt the backup.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Encrypted Backup",
            os.path.expanduser("~/bingo_backup.bingo"),
            "Bingo Backup Files (*.bingo)",
        )
        if file_path:
            self.export_requested.emit(file_path, pwd)
            self.exp_pass.clear()

    def _browse_import_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Backup File",
            os.path.expanduser("~"),
            "Bingo Backup Files (*.bingo)",
        )
        if file_path:
            self.imp_file_edit.setText(file_path)

    def _on_import(self) -> None:
        f = self.imp_file_edit.text().strip()
        pwd = self.imp_pass.text()
        mode = self.mode_combo.currentData()

        if not f or not os.path.exists(f):
            QMessageBox.warning(self, "File Not Found", "Please choose a valid .bingo backup file.")
            return
        if not pwd:
            QMessageBox.warning(self, "Password Required", "Please enter the backup password.")
            return

        self.import_requested.emit(f, pwd, mode)
        self.imp_pass.clear()
