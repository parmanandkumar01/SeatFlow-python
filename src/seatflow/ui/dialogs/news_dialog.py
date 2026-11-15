"""Dialog for displaying railway bulletins, circulars, and system announcements.

Matches the original desktop application's News interface (news.html) with:
- Categorized announcement list (announcement, circular, security)
- Urgent priority indicators and highlight banners
- Detailed announcement viewer with structured content
- User acknowledgment tracking per item and batch
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seatflow.services.news_service import NewsService


class NewsDialog(QDialog):
    """Modal dialog for viewing and acknowledging railway announcements."""

    news_read = Signal(str)

    def __init__(
        self,
        news_service: NewsService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._service = news_service
        self._current_news_id: Optional[str] = None

        self.setWindowTitle("Railway Bulletins & Announcements")
        self.setMinimumSize(780, 520)
        self.setModal(True)

        self._setup_ui()
        self._setup_styles()
        self._populate_list()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("Bulletins & Announcements")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #ffffff; background: transparent;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #b0b0b0; border: none; font-size: 16px; }"
            "QPushButton:hover { color: #ffffff; background: #3d3d3d; border-radius: 15px; }"
        )
        close_btn.clicked.connect(self.accept)
        header_layout.addWidget(close_btn)
        main_layout.addLayout(header_layout)

        # Splitter with list and details
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: #3d3d3d; }")

        # Left list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)

        lbl_list = QLabel("Announcements")
        lbl_list.setStyleSheet("color: #b0b0b0; font-size: 12px; font-weight: bold;")
        left_layout.addWidget(lbl_list)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "QListWidget { background: #252525; border: 1px solid #3d3d3d; border-radius: 6px; padding: 4px; }"
            "QListWidget::item { padding: 8px; border-bottom: 1px solid #2f2f2f; color: #ffffff; border-radius: 4px; }"
            "QListWidget::item:selected { background: #333d4d; color: #42a5f5; }"
            "QListWidget::item:hover { background: #2c2c2c; }"
        )
        self.list_widget.currentRowChanged.connect(self._on_item_selected)
        left_layout.addWidget(self.list_widget)

        splitter.addWidget(left_widget)

        # Right details pane
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(10)

        # Detail header row
        self.detail_title = QLabel("Select an announcement")
        title_f = QFont()
        title_f.setPointSize(14)
        title_f.setBold(True)
        self.detail_title.setFont(title_f)
        self.detail_title.setStyleSheet("color: #ffffff; background: transparent;")
        self.detail_title.setWordWrap(True)
        right_layout.addWidget(self.detail_title)

        meta_row = QHBoxLayout()
        self.lbl_category = QLabel("")
        self.lbl_category.setStyleSheet(
            "background: #1976d2; color: #ffffff; border-radius: 3px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        self.lbl_date = QLabel("")
        self.lbl_date.setStyleSheet("color: #888888; font-size: 11px;")
        meta_row.addWidget(self.lbl_category)
        meta_row.addWidget(self.lbl_date)
        meta_row.addStretch()
        right_layout.addLayout(meta_row)

        # Urgent banner
        self.urgent_banner = QFrame()
        self.urgent_banner.setStyleSheet(
            "QFrame { background: #4a2800; border: 1px solid #ff9800; border-radius: 4px; padding: 6px; }"
        )
        u_layout = QHBoxLayout(self.urgent_banner)
        u_layout.setContentsMargins(8, 4, 8, 4)
        lbl_u = QLabel("⚠️ PRIORITY NOTICE: High importance")
        lbl_u.setStyleSheet("color: #ffb74d; font-size: 11px; font-weight: bold;")
        u_layout.addWidget(lbl_u)
        self.urgent_banner.setVisible(False)
        right_layout.addWidget(self.urgent_banner)

        # Content area
        self.detail_content = QTextEdit()
        self.detail_content.setReadOnly(True)
        self.detail_content.setStyleSheet(
            "QTextEdit { background: #222222; color: #e0e0e0; border: 1px solid #3d3d3d; "
            "border-radius: 6px; padding: 10px; font-size: 13px; line-height: 1.5; }"
        )
        right_layout.addWidget(self.detail_content)

        # Item action row
        action_row = QHBoxLayout()
        action_row.addStretch()
        self.btn_acknowledge = QPushButton("I Understand / Mark as Read")
        self.btn_acknowledge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_acknowledge.setStyleSheet(
            "QPushButton { background: #4caf50; color: #ffffff; border: none; "
            "border-radius: 4px; padding: 8px 16px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #66bb6a; }"
            "QPushButton:disabled { background: #2b3b2c; color: #888888; }"
        )
        self.btn_acknowledge.clicked.connect(self._on_acknowledge_clicked)
        action_row.addWidget(self.btn_acknowledge)
        right_layout.addLayout(action_row)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter)

        # Bottom bar
        bottom_row = QHBoxLayout()
        self.lbl_unread_summary = QLabel("")
        self.lbl_unread_summary.setStyleSheet("color: #b0b0b0; font-size: 12px;")
        bottom_row.addWidget(self.lbl_unread_summary)
        bottom_row.addStretch()

        self.btn_ack_all = QPushButton("Acknowledge All")
        self.btn_ack_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ack_all.setStyleSheet(
            "QPushButton { background: #3d3d3d; color: #ffffff; border: 1px solid #4d4d4d; "
            "border-radius: 4px; padding: 6px 14px; font-size: 12px; }"
            "QPushButton:hover { background: #4a4a4a; }"
        )
        self.btn_ack_all.clicked.connect(self._on_ack_all_clicked)
        bottom_row.addWidget(self.btn_ack_all)

        btn_done = QPushButton("Close")
        btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_done.setStyleSheet(
            "QPushButton { background: #42a5f5; color: #ffffff; border: none; "
            "border-radius: 4px; padding: 6px 18px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #54b3f6; }"
        )
        btn_done.clicked.connect(self.accept)
        bottom_row.addWidget(btn_done)

        main_layout.addLayout(bottom_row)

    def _setup_styles(self) -> None:
        self.setStyleSheet(
            "QDialog { background-color: #1e1e1e; }"
            "QLabel { background: transparent; }"
        )

    def _populate_list(self) -> None:
        self.list_widget.clear()
        news_items = self._service.get_all_news()

        for idx, item in enumerate(news_items):
            title = item.get("title", "Untitled")
            is_ack = item.get("is_acknowledged", False)
            is_urgent = item.get("urgent", False)

            prefix = "✔ " if is_ack else "● "
            if is_urgent and not is_ack:
                prefix = "⚠️ "

            list_item = QListWidgetItem(f"{prefix}{title}")
            list_item.setData(Qt.ItemDataRole.UserRole, item.get("id"))
            if not is_ack:
                font = list_item.font()
                font.setBold(True)
                list_item.setFont(font)
            self.list_widget.addItem(list_item)

        unread = self._service.unread_count()
        if unread > 0:
            self.lbl_unread_summary.setText(f"{unread} unread announcement(s)")
            self.btn_ack_all.setEnabled(True)
        else:
            self.lbl_unread_summary.setText("All announcements acknowledged")
            self.btn_ack_all.setEnabled(False)

        if news_items:
            self.list_widget.setCurrentRow(0)

    def _on_item_selected(self, row: int) -> None:
        if row < 0:
            return
        item_widget = self.list_widget.item(row)
        if not item_widget:
            return

        news_id = item_widget.data(Qt.ItemDataRole.UserRole)
        self._current_news_id = news_id

        try:
            item = self._service.get_news_by_id(news_id)
        except Exception:
            return

        self.detail_title.setText(item.get("title", ""))
        category = item.get("category", "General").upper()
        self.lbl_category.setText(category)
        self.lbl_date.setText(item.get("date", ""))
        self.urgent_banner.setVisible(bool(item.get("urgent")))
        self.detail_content.setPlainText(item.get("content", ""))

        is_ack = item.get("is_acknowledged", False)
        if is_ack:
            self.btn_acknowledge.setEnabled(False)
            self.btn_acknowledge.setText("Acknowledged ✔")
        else:
            self.btn_acknowledge.setEnabled(True)
            self.btn_acknowledge.setText("I Understand / Mark as Read")

    def _on_acknowledge_clicked(self) -> None:
        if not self._current_news_id:
            return
        self._service.acknowledge_news(self._current_news_id)
        self.news_read.emit(self._current_news_id)
        self._populate_list()

    def _on_ack_all_clicked(self) -> None:
        self._service.acknowledge_all()
        self._populate_list()
