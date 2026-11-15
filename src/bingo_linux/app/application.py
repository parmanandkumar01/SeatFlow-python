"""Application bootstrap and dependency wiring."""

from __future__ import annotations

import json
import os
import webbrowser
from typing import Any, Optional

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMessageBox,
    QWidget,
)

from bingo_linux.database.database import Database
from bingo_linux.security.vault import VaultService
from bingo_linux.services import (
    BookingState,
    BookingWorkflowService,
    CleanerService,
    HistoryService,
    IrctcAccountService,
    InvalidTransitionError,
    MasterDataService,
    NewsService,
    PaymentService,
    PnrService,
    ProxyService,
    SettingsService,
    TicketService,
    TransferService,
)
from bingo_linux.services.ticket_render_service import TicketRenderService
from bingo_linux.services.train_service import check_availability, fetch_train_list
from bingo_linux.ui import (
    AccountsWindow,
    BackupRestoreWindow,
    BookWindow,
    HistoryWindow,
    MainToolbarWindow,
    MainWindow,
    PaymentWindow,
    ProxiesWindow,
    SettingsWindow,
    TicketPanelWindow,
    TicketsWindow,
    TokensWindow,
    TrainResultsWindow,
    UpdateWindow,
    VaultWindow,
    place_toolbar_top,
)
from bingo_linux.ui.dialogs.captcha_dialog import CaptchaDialog
from bingo_linux.ui.dialogs.fare_confirm_dialog import FareConfirmDialog
from bingo_linux.ui.dialogs.two_factor_dialog import TwoFactorDialog
from bingo_linux.ui.theme import DARK_THEME_STYLE


class Application(QObject):
    """Main application controller that wires UI windows and services together.

    Emits signals for application lifecycle events.
    """

    #: Emitted when the application is ready to show the main window.
    ready = Signal()

    #: Emitted when the vault has been unlocked and the main app is shown.
    unlocked = Signal()

    #: Emitted when the application is shutting down.
    shutting_down = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._db: Optional[Database] = None
        self._vault: Optional[VaultService] = None
        self._account_service: Optional[IrctcAccountService] = None
        self._ticket_service: Optional[TicketService] = None
        self._history_service: Optional[HistoryService] = None
        self._pnr_service: Optional[PnrService] = None
        self._proxy_service: Optional[ProxyService] = None
        self._settings_service: Optional[SettingsService] = None
        self._transfer_service: Optional[TransferService] = None
        self._news_service: Optional[NewsService] = None
        self._payment_service: Optional[PaymentService] = None
        self._master_data_service: Optional[MasterDataService] = None
        self._booking_service: Optional[BookingWorkflowService] = None
        self._cleaner_service: Optional[CleanerService] = None
        self._ticket_render_service: Optional[TicketRenderService] = None
        self._ers_output_dir: str = os.path.join(os.getcwd(), "ers_records")
        self._active_pair_key: Optional[str] = None

        # UI Window instances
        self._main_window: Optional[MainToolbarWindow] = None
        self._book_window: Optional[BookWindow] = None
        self._tickets_window: Optional[TicketsWindow] = None
        self._train_results_window: Optional[TrainResultsWindow] = None
        self._accounts_window: Optional[AccountsWindow] = None
        self._payment_window: Optional[PaymentWindow] = None
        self._settings_window: Optional[SettingsWindow] = None
        self._proxies_window: Optional[ProxiesWindow] = None
        self._history_window: Optional[HistoryWindow] = None
        self._backup_restore_window: Optional[BackupRestoreWindow] = None
        self._tokens_window: Optional[TokensWindow] = None
        self._pair_windows: dict[str, TicketPanelWindow] = {}
        self._vault_window: Optional[VaultWindow] = None
        self._update_window: Optional[UpdateWindow] = None

    def _initialize_services(self) -> None:
        """Initialize database, vault, and service layer."""
        if self._db is None:
            self._db = Database()
            self._db.initialize_schema()

        if self._vault is None:
            self._vault = VaultService(self._db)
            if not self._vault.is_configured():
                try:
                    self._vault.initialize("bingo-pro-master-key")
                except Exception:
                    pass
            elif not self._vault.is_unlocked():
                try:
                    self._vault.unlock("bingo-pro-master-key")
                except Exception:
                    pass

        self._account_service = IrctcAccountService(self._db, self._vault)
        self._ticket_service = TicketService(self._db)
        self._history_service = HistoryService(self._db)
        self._pnr_service = PnrService(self._db)
        self._proxy_service = ProxyService(self._db, self._vault)
        self._settings_service = SettingsService(self._db, self._vault)
        self._transfer_service = TransferService(self._db, self._vault)
        self._news_service = NewsService(self._db)
        self._payment_service = PaymentService(self._db)
        self._master_data_service = MasterDataService()
        self._cleaner_service = CleanerService()
        self._booking_service = BookingWorkflowService(
            self._db,
            history_service=self._history_service,
            pnr_service=self._pnr_service,
            ticket_service=self._ticket_service,
            account_service=self._account_service,
        )
        self._ticket_render_service = TicketRenderService()

    def create_main_window(self) -> MainWindow:
        """Create and return the main application window.

        If the vault is locked or unconfigured, the VaultWindow is shown
        first; the main toolbar is created only after the vault is unlocked.
        """
        if self._main_window is None:
            qapp = QApplication.instance()
            if qapp is not None:
                qapp.setStyleSheet(DARK_THEME_STYLE)

            self._initialize_services()

            # Vault gate: show VaultWindow unless vault is already unlocked.
            if not self._vault.is_unlocked():
                self._create_vault_window()
                # Return a lightweight placeholder so callers get a QWidget.
                # The real main window is created after vault unlock.
                return self._vault_window  # type: ignore[return-value]

            self._main_window = MainToolbarWindow()
            place_toolbar_top(self._main_window)

            # Secondary floating windows
            self._create_floating_windows()
            self._connect_signals()

            # Position tickets window below toolbar
            self._position_window_centered(self._tickets_window, top_offset=90)
            self._refresh_tickets_window()

        return self._main_window

    def _create_vault_window(self) -> None:
        """Create and show the VaultWindow, gating access to the main app."""
        self._vault_window = VaultWindow()
        self._vault_window.set_vault(self._vault)
        self._vault_window.set_mode(
            "setup" if not self._vault.is_configured() else "unlock"
        )
        self._vault_window.unlocked.connect(self._on_vault_unlocked)
        self._vault_window.quit_requested.connect(self.shutdown)
        self._vault_window.show()

    def _on_vault_unlocked(self) -> None:
        """Handle the VaultWindow unlocked signal.

        Creates the main toolbar and floating windows once the vault is
        unlocked and configured, then hides the vault gate.
        """
        if not (self._vault.is_configured() and self._vault.is_unlocked()):
            # Not actually ready (e.g. reset just switched to setup mode).
            return

        # Tear down the vault gate.
        if self._vault_window is not None:
            self._vault_window.hide()
            self._vault_window.deleteLater()
            self._vault_window = None

        self._create_all_windows()
        if self._main_window is not None:
            self._main_window.show()
        self.unlocked.emit()

    def show_update_window(self) -> Optional[UpdateWindow]:
        """Create and show the local-only UpdateWindow, or return the existing one.

        PRIVACY (default-deny): The UpdateWindow performs zero vendor network
        calls. It is opened only on explicit user action and never invoked
        automatically during application startup or in the background.
        """
        if self._update_window is None:
            self._update_window = UpdateWindow()
            self._update_window.checking.connect(
                lambda: self.event_emitted.emit("update_checking", "Checking for updates…")
            )
            self._update_window.downloading.connect(
                lambda: self.event_emitted.emit("update_downloading", "Downloading update…")
            )
            self._update_window.installing.connect(
                lambda: self.event_emitted.emit("update_installing", "Installing update…")
            )
            self._update_window.restarting.connect(
                lambda: self.event_emitted.emit("update_restarting", "Restarting application…")
            )
            self._update_window.completed.connect(
                lambda: self.event_emitted.emit("update_completed", "Update complete.")
            )
            self._update_window.failed.connect(
                lambda reason: self.event_emitted.emit("update_failed", f"Update failed: {reason}")
            )
        self._update_window.show()
        return self._update_window

    def _create_floating_windows(self) -> None:
        """Create all secondary floating windows (extracted for reuse)."""
        self._book_window = BookWindow(master_data_service=self._master_data_service)
        self._tickets_window = TicketsWindow()
        self._train_results_window = TrainResultsWindow()
        self._accounts_window = AccountsWindow()
        self._payment_window = PaymentWindow()
        self._settings_window = SettingsWindow()
        self._proxies_window = ProxiesWindow()
        self._history_window = HistoryWindow()
        self._backup_restore_window = BackupRestoreWindow()
        self._tokens_window = TokensWindow()

        # All secondary floating windows start hidden. Only the main toolbar
        # (or VaultWindow when the vault is locked) is shown at startup.
        self._hide_all_floating_windows()

    def _hide_all_floating_windows(self) -> None:
        """Hide every secondary floating window so none leaks at startup."""
        for w in [
            self._book_window,
            self._tickets_window,
            self._train_results_window,
            self._accounts_window,
            self._payment_window,
            self._settings_window,
            self._proxies_window,
            self._history_window,
            self._backup_restore_window,
            self._tokens_window,
        ]:
            if w is not None:
                try:
                    w.hide()
                except Exception:
                    pass

    def _create_all_windows(self) -> None:
        """Create the main toolbar and all secondary floating windows."""
        self._main_window = MainToolbarWindow()
        place_toolbar_top(self._main_window)

        self._create_floating_windows()
        self._connect_signals()

        # Position tickets window below toolbar
        self._position_window_centered(self._tickets_window, top_offset=90)
        self._refresh_tickets_window()

    def _connect_signals(self) -> None:
        """Connect UI signals between windows and services."""
        if self._main_window is None:
            return

        # Main toolbar actions
        self._main_window.action_clicked.connect(self._on_action_clicked)
        self._main_window.close_requested.connect(self.shutdown)
        self._main_window.exit_requested.connect(self.shutdown)

        # Book window signals
        if self._book_window is not None:
            self._book_window.search_clicked.connect(self._on_search_trains)
            self._book_window.availability_clicked.connect(self._on_check_availability)
            self._book_window.save_clicked.connect(self._on_save_ticket)

        # Train results window
        if self._train_results_window is not None:
            self._train_results_window.apply_selection.connect(self._on_train_selected)

        # Tickets window signals
        if self._tickets_window is not None:
            self._tickets_window.open_ticket.connect(self._on_open_ticket)
            self._tickets_window.edit_ticket.connect(self._on_edit_ticket)
            self._tickets_window.duplicate_ticket.connect(self._on_duplicate_ticket)
            self._tickets_window.delete_ticket.connect(self._on_delete_ticket)
            self._tickets_window.delete_all.connect(self._on_delete_all_tickets)
            self._tickets_window.history_clicked.connect(self._on_show_history)
            self._tickets_window.generate_tokens_clicked.connect(self._on_action_tokens)
            self._tickets_window.launch_all.connect(self._on_launch_all_tickets)

        # Accounts window signals
        if self._accounts_window is not None:
            self._accounts_window.add_account.connect(self._on_add_account)
            self._accounts_window.bulk_import.connect(self._on_bulk_import_accounts)
            self._accounts_window.delete_account.connect(self._on_delete_account)
            self._accounts_window.toggle_active.connect(self._on_toggle_account_active)

        # Payment window signals
        if self._payment_window is not None:
            self._payment_window.add_payment.connect(self._on_add_payment)
            self._payment_window.delete_payment.connect(self._on_delete_payment)

        # Settings window signals
        if self._settings_window is not None:
            self._settings_window.proxy_clicked.connect(self._on_show_proxies)
            self._settings_window.freecharge_clicked.connect(self._on_show_payment)
            self._settings_window.backup_restore_clicked.connect(self._on_show_backup_restore)
            self._settings_window.cleanup_clicked.connect(self._on_cleanup_cache)
            self._settings_window.manual_login_changed.connect(self._on_manual_login_changed)

        # Proxies window signals
        if self._proxies_window is not None:
            self._proxies_window.add_proxy.connect(self._on_add_proxy)
            self._proxies_window.delete_proxy.connect(self._on_delete_proxy)
            self._proxies_window.test_proxy.connect(self._on_test_proxy)

        # Backup & restore window signals
        if self._backup_restore_window is not None:
            self._backup_restore_window.export_requested.connect(self._on_export_backup)
            self._backup_restore_window.import_requested.connect(self._on_import_backup)

        # Tokens window signals
        if self._tokens_window is not None:
            self._tokens_window.check_clicked.connect(self._on_check_tokens)
            self._tokens_window.clear_clicked.connect(self._on_clear_tokens)

        # Booking workflow service signals (user-driven checkpoints).
        if self._booking_service is not None:
            self._booking_service.state_changed.connect(
                self._on_booking_state_changed
            )
            self._booking_service.waiting_for_2fa.connect(
                self._on_booking_waiting_for_2fa
            )
            self._booking_service.waiting_for_captcha.connect(
                self._on_booking_waiting_for_captcha
            )
            self._booking_service.waiting_for_fare_confirmation.connect(
                self._on_booking_waiting_for_fare
            )
            self._booking_service.booking_completed.connect(
                self._on_booking_completed
            )
            self._booking_service.booking_failed.connect(
                self._on_booking_failed
            )
            self._booking_service.booking_cancelled.connect(
                self._on_booking_cancelled
            )

    # ------------------------------------------------------------------
    # Positioning Helpers
    # ------------------------------------------------------------------

    def _position_window_centered(self, win: QWidget, top_offset: int = 100) -> None:
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        w = win.width()
        x = geo.x() + (geo.width() - w) // 2
        y = geo.y() + top_offset
        win.move(max(geo.x(), x), max(geo.y(), y))

    # ------------------------------------------------------------------
    # Action Routing
    # ------------------------------------------------------------------

    def _on_action_clicked(self, action: str) -> None:
        if action in ("tickets", "brand"):
            self._on_show_tickets()
        elif action == "book":
            self._on_show_book()
        elif action == "tokens":
            self._on_action_tokens()
        elif action == "settings":
            self._on_toggle_settings()
        elif action == "accounts":
            self._on_show_accounts()
        elif action == "payment":
            self._on_show_payment()

    def _on_show_book(self) -> None:
        if self._book_window is None:
            return
        if self._account_service is not None:
            self._book_window.set_accounts(self._account_service.list_accounts())
        if self._proxy_service is not None:
            self._book_window.set_proxies(self._proxy_service.list_proxies())
        if self._payment_service is not None:
            self._book_window.set_payments(self._payment_service.list_methods())
        self._position_window_centered(self._book_window, top_offset=90)
        self._book_window.show()
        self._book_window.raise_()

    def _on_show_tickets(self) -> None:
        if self._tickets_window is None:
            return
        self._refresh_tickets_window()
        self._position_window_centered(self._tickets_window, top_offset=90)
        self._tickets_window.show()
        self._tickets_window.raise_()

    def _on_action_tokens(self) -> None:
        if self._tokens_window is None:
            return
        self._position_window_centered(self._tokens_window, top_offset=90)
        self._tokens_window.show()
        self._tokens_window.raise_()

    def _on_check_tokens(self) -> None:
        if self._tokens_window is not None:
            self._tokens_window.apply_check_result({
                "userId": "PRO-ACTIVE",
                "count": "Unlimited",
                "httpOk": True,
            })

    def _on_clear_tokens(self) -> None:
        if self._tokens_window is not None:
            self._tokens_window.apply_check_result({
                "userId": "PRO-ACTIVE",
                "count": "0",
                "httpOk": True,
            })

    def _on_toggle_settings(self) -> None:
        if self._settings_window is None or self._main_window is None:
            return
        if self._settings_window.isVisible():
            self._settings_window.hide()
        else:
            btn_pos = self._main_window.btn_settings.mapToGlobal(
                QPoint(0, self._main_window.btn_settings.height() + 8)
            )
            self._settings_window.move(btn_pos)
            self._settings_window.show()
            self._settings_window.raise_()

    def _on_show_accounts(self) -> None:
        if self._accounts_window is None or self._account_service is None:
            return
        self._accounts_window.set_accounts(self._account_service.list_accounts())
        self._position_window_centered(self._accounts_window, top_offset=90)
        self._accounts_window.show()
        self._accounts_window.raise_()

    def _on_show_payment(self) -> None:
        if self._payment_window is None or self._payment_service is None:
            return
        self._payment_window.set_payments(self._payment_service.list_methods())
        self._position_window_centered(self._payment_window, top_offset=90)
        self._payment_window.show()
        self._payment_window.raise_()

    def _on_show_proxies(self) -> None:
        if self._proxies_window is None or self._proxy_service is None:
            return
        self._proxies_window.set_proxies(self._proxy_service.list_proxies())
        self._position_window_centered(self._proxies_window, top_offset=90)
        self._proxies_window.show()
        self._proxies_window.raise_()
        if self._settings_window is not None:
            self._settings_window.hide()

    def _on_show_history(self) -> None:
        if self._history_window is None or self._history_service is None:
            return
        self._history_window.set_records(self._history_service.list_history())
        self._position_window_centered(self._history_window, top_offset=90)
        self._history_window.show()
        self._history_window.raise_()

    def _on_show_backup_restore(self) -> None:
        if self._backup_restore_window is None:
            return
        self._position_window_centered(self._backup_restore_window, top_offset=90)
        self._backup_restore_window.show()
        self._backup_restore_window.raise_()
        if self._settings_window is not None:
            self._settings_window.hide()

    def _on_cleanup_cache(self) -> None:
        if self._settings_window is not None:
            self._settings_window.hide()
        stats = {}
        if self._cleaner_service is not None:
            try:
                stats = self._cleaner_service.clean_all()
            except Exception:
                pass
        mb = stats.get("mb_freed", 0.0)
        files = stats.get("files_removed", 0)
        msg = f"Cleaned {files} files ({mb} MB freed).\nLocal temporary caches and history clean up completed."
        parent = self._settings_window or self._main_window
        if parent is not None:
            QMessageBox.information(parent, "Clean Up", msg)

    def _on_manual_login_changed(self, enabled: bool) -> None:
        if self._settings_service is not None:
            try:
                self._settings_service.set("manual_login", "1" if enabled else "0")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Booking & Train Search Logic
    # ------------------------------------------------------------------

    def _on_search_trains(self) -> None:
        if self._book_window is None or self._train_results_window is None:
            return

        from_stn = self._book_window.from_edit.text()
        to_stn = self._book_window.to_edit.text()
        date_str = self._book_window.date_edit.date().toString("yyyy-MM-dd")

        from_code = BookWindow._clean_station(from_stn)
        to_code = BookWindow._clean_station(to_stn)

        if not from_code or not to_code:
            QMessageBox.warning(
                self._book_window,
                "Validation Error",
                "Please enter both From and To stations.",
            )
            return

        query = {"from": from_code, "to": to_code, "date": date_str}
        self._train_results_window.set_loading(query)
        self._position_window_centered(self._train_results_window, top_offset=90)
        self._train_results_window.show()
        self._train_results_window.raise_()

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            res = fetch_train_list(from_code, to_code, date_str, query=query)
            trains = res.get("trains", []) if isinstance(res, dict) else (res if isinstance(res, list) else [])
        except Exception:
            trains = []
        finally:
            QGuiApplication.restoreOverrideCursor()

        if trains:
            self._train_results_window.set_trains(trains, query)
        else:
            self._train_results_window.set_error(
                f"No trains found between {from_code} and {to_code} on {date_str}."
            )

    def _on_check_availability(self) -> None:
        if self._book_window is None or self._train_results_window is None:
            return

        from_stn = self._book_window.from_edit.text()
        to_stn = self._book_window.to_edit.text()
        date_str = self._book_window.date_edit.date().toString("yyyy-MM-dd")

        from_code = BookWindow._clean_station(from_stn)
        to_code = BookWindow._clean_station(to_stn)
        if not from_code or not to_code:
            QMessageBox.warning(
                self._book_window,
                "Validation Error",
                "Please enter both From and To stations.",
            )
            return

        train_no = self._book_window._clean_train_no(self._book_window.train_edit.text())
        cls = self._book_window.class_combo.currentData() or ""
        quota = self._book_window.quota_combo.currentData() or "GN"

        query = {"from": from_code, "to": to_code, "date": date_str}
        self._train_results_window.set_loading(query)
        self._position_window_centered(self._train_results_window, top_offset=90)
        self._train_results_window.show()
        self._train_results_window.raise_()

        if train_no and cls:
            try:
                res = check_availability(
                    train_no,
                    from_code,
                    to_code,
                    date_str,
                    travel_class=cls,
                    quota=quota,
                )
                status = res.get("status", "")
                fare = res.get("fare")
                is_avail = bool(res.get("is_available", False))
                dot = "🟢" if is_avail else "🟡"
                text = f"{dot} {status} | ₹{fare:,} | {quota}"
                self._book_window.set_availability_status(
                    text, is_available=is_avail, fare=fare
                )
            except Exception as exc:
                self._book_window.set_availability_status(
                    f"⚠️ CHECK FAILED: {exc}", is_available=False
                )
        else:
            self._train_results_window.banner_text.setText(
                f"CHECKING AVAILABILITY FOR {from_code} → {to_code}..."
            )

    def _on_train_selected(self, selection: dict) -> None:
        if self._book_window is not None:
            self._book_window.apply_train_selection(selection)
            self._book_window.raise_()

    def _on_save_ticket(self, data: dict) -> None:
        if self._ticket_service is None:
            return
        tid = data.get("id")
        try:
            if tid:
                self._ticket_service.update_ticket(
                    ticket_id=tid,
                    train_number=data["train_number"],
                    from_station=data["from_station"],
                    to_station=data["to_station"],
                    journey_date=data["journey_date"],
                    class_type=data["class"],
                    quota=data["quota"],
                    passenger_details=data["passenger_details"],
                    mobile=data.get("mobile"),
                    irctc_account_id=data.get("irctc_account_id"),
                )
            else:
                self._ticket_service.add_ticket(
                    train_number=data["train_number"],
                    from_station=data["from_station"],
                    to_station=data["to_station"],
                    journey_date=data["journey_date"],
                    class_type=data["class"],
                    quota=data["quota"],
                    passenger_details=data["passenger_details"],
                    mobile=data.get("mobile"),
                    irctc_account_id=data.get("irctc_account_id"),
                )
            self._refresh_tickets_window()
            if self._tickets_window is not None:
                self._tickets_window.show()
                self._tickets_window.raise_()
        except Exception as e:
            if self._book_window is not None:
                QMessageBox.warning(self._book_window, "Error Saving Ticket", str(e))

    def _refresh_tickets_window(self) -> None:
        if self._ticket_service is None or self._tickets_window is None:
            return
        raw_tickets = self._ticket_service.list_tickets()
        formatted = []
        for t in raw_tickets:
            item = dict(t)
            if not item.get("ticket_name"):
                pax_str = item.get("passenger_details", "")
                suffix = ""
                try:
                    pax = json.loads(pax_str)
                    if isinstance(pax, list) and pax:
                        name_parts = str(pax[0].get("name", "")).strip().split()
                        if name_parts:
                            suffix = f"_{name_parts[-1].lower()}"
                except Exception:
                    pass
                item["ticket_name"] = (
                    f"{str(item.get('from_station', '')).lower()}_"
                    f"{str(item.get('to_station', '')).lower()}{suffix}"
                )
            formatted.append(item)
        self._tickets_window.set_tickets(formatted)

    def _on_open_ticket(self, ticket_id: str, pair_idx: int) -> None:
        if self._ticket_service is None:
            return
        try:
            ticket = self._ticket_service.get_ticket(ticket_id)
        except Exception:
            return

        pair_key = f"{ticket_id}_{pair_idx}"
        if pair_key in self._pair_windows:
            self._pair_windows[pair_key].show()
            self._pair_windows[pair_key].raise_()
            return

        pair_win = TicketPanelWindow(ticket=ticket, pair_index=pair_idx)
        if self._account_service is not None:
            pair_win.set_accounts(self._account_service.list_accounts())
        if self._proxy_service is not None:
            pair_win.set_proxies(self._proxy_service.list_proxies())
        if self._payment_service is not None:
            pair_win.set_payments(self._payment_service.list_methods())

        pair_win.close_clicked.connect(lambda tid, idx: self._on_pair_closed(tid, idx))
        pair_win.launch_worker.connect(self._on_pair_launch_worker)

        offset = 120 + (len(self._pair_windows) % 5) * 30
        self._position_window_centered(pair_win, top_offset=offset)
        pair_win.show()
        pair_win.raise_()
        self._pair_windows[pair_key] = pair_win

    def _on_pair_closed(self, ticket_id: str, pair_idx: int) -> None:
        pair_key = f"{ticket_id}_{pair_idx}"
        self._pair_windows.pop(pair_key, None)

    def _on_pair_launch_worker(self, ticket_id: str, pair_idx: int, worker_tag: str) -> None:
        """Handle a worker-button launch from a ticket pair panel.

        Starts the user-assisted booking session, opens the official IRCTC
        page in the system browser (sanctioned visible browser, no
        automation), copies passenger/train details to the clipboard for
        form assistance, and advances the workflow to the manual login /
        2FA checkpoint.
        """
        pair_key = f"{ticket_id}_{pair_idx}"
        win = self._pair_windows.get(pair_key)
        if (
            win is None
            or self._booking_service is None
            or self._ticket_service is None
        ):
            return

        self._active_pair_key = pair_key

        try:
            self._booking_service.start_session(ticket_id)
        except InvalidTransitionError:
            # A session is already active; continue with the handoff.
            pass

        ticket = self._ticket_service.get_ticket(ticket_id)

        # 2. Browser launch handoff — sanctioned visible system browser.
        self._open_browser(self._irctc_booking_url())

        win.set_status(f"ACTIVE · {worker_tag} · BROWSER OPENED", "#06b6d4")
        win.set_availability("VERIFYING · LOGIN", is_available=False)
        win.set_tatkal_countdown(ticket.get("class"))

        # 3. Form assistance — copy passenger/train details to clipboard.
        self._copy_booking_details_to_clipboard(ticket)

        # 4. Advance to the manual login / 2FA checkpoint.
        self._booking_service.reach_login_checkpoint()

    def _irctc_booking_url(self) -> str:
        """Return the official IRCTC booking page URL."""
        return "https://www.irctc.co.in/ntrain/train"

    def _open_browser(self, url: str) -> None:
        """Open a URL in the system's default visible browser.

        No automation or headless fetching is performed; the user
        completes login, CAPTCHA, and payment manually in the browser.
        """
        try:
            webbrowser.open(url, new=1, autoraise=True)
        except Exception:
            pass

    def _copy_booking_details_to_clipboard(self, ticket: dict[str, Any]) -> None:
        """Copy passenger and train details to the clipboard for form entry."""
        passengers = ""
        try:
            pax_list = json.loads(ticket.get("passenger_details", "[]") or "[]")
            if isinstance(pax_list, list):
                passengers = "; ".join(
                    f"{p.get('name', '')} "
                    f"({p.get('age', '')}, {p.get('gender', '')}, "
                    f"{p.get('berth', p.get('berth_preference', ''))})"
                    for p in pax_list
                    if isinstance(p, dict)
                )
        except Exception:
            passengers = str(ticket.get("passenger_details", ""))

        text = (
            f"Train {ticket.get('train_number', '')} | "
            f"{ticket.get('from_station', '')} → {ticket.get('to_station', '')} | "
            f"{ticket.get('journey_date', '')} | "
            f"{ticket.get('class', '')} | {ticket.get('quota', '')}\n"
            f"Passengers: {passengers}\n"
            "Enter these details manually on the IRCTC booking page."
        )
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _active_pair_window(self) -> Optional[TicketPanelWindow]:
        """Return the pair panel driving the active booking session."""
        key = self._active_pair_key
        if key is None:
            return None
        return self._pair_windows.get(key)

    def _on_booking_state_changed(self, old: str, new: str) -> None:
        """Reflect booking state transitions on the active pair panel."""
        win = self._active_pair_window()
        if win is None or self._booking_service is None:
            return
        try:
            state = BookingState(new)
        except ValueError:
            return
        win.set_booking_state(state)
        if state == BookingState.IN_PROGRESS and self._ticket_service is not None:
            ticket_id = (self._booking_service.session or {}).get("ticket_id")
            if ticket_id:
                try:
                    ticket = self._ticket_service.get_ticket(ticket_id)
                    win.set_tatkal_countdown(ticket.get("class"))
                except Exception:
                    pass

    def _on_booking_waiting_for_2fa(self) -> None:
        """2FA checkpoint: prompt the user for manual OTP entry."""
        win = self._active_pair_window()
        if win is not None:
            win.set_status("WAITING · 2FA / OTP", "#ea580c")
        code = self._show_two_factor_dialog(win)
        if code and self._booking_service is not None:
            try:
                self._booking_service.submit_manual_2fa(code)
            except Exception as exc:
                self._show_booking_error(win, f"2FA rejected: {exc}")

    def _on_booking_waiting_for_captcha(self) -> None:
        """CAPTCHA checkpoint: prompt the user to enter the on-screen CAPTCHA."""
        win = self._active_pair_window()
        if win is not None:
            win.set_status("WAITING · CAPTCHA", "#f59e0b")
        text = self._show_captcha_dialog(win)
        if text and self._booking_service is not None:
            try:
                self._booking_service.submit_manual_captcha(text)
            except Exception as exc:
                self._show_booking_error(win, f"CAPTCHA rejected: {exc}")

    def _on_booking_waiting_for_fare(self) -> None:
        """Fare/payment checkpoint: show payment details and confirm fare."""
        win = self._active_pair_window()
        if win is not None:
            win.set_status("PAYMENT · PENDING", "#7c3aed")
        self._show_payment_details(win)
        confirmed = self._show_fare_confirm_dialog(win)
        if self._booking_service is None:
            return
        try:
            if confirmed:
                self._booking_service.confirm_fare(True)
            else:
                self._booking_service.confirm_fare(False)
        except Exception as exc:
            self._show_booking_error(win, f"Fare confirmation failed: {exc}")

    def _on_booking_completed(self, pnr: str) -> None:
        """Booking completed: update panel, render ERS, and notify the user."""
        win = self._active_pair_window()
        if win is not None:
            win.set_status("BOOKED", "#16a34a")
            win.set_availability("BOOKED", is_available=False)
        self._render_and_save_ers(pnr)
        parent = win or self._main_window
        if parent is not None:
            QMessageBox.information(
                parent,
                "Booking Complete",
                f"Booking completed successfully!\nPNR: {pnr}\n"
                f"ERS slip saved to {self._ers_output_dir}.",
            )

    def _on_booking_failed(self, reason: str) -> None:
        """Handle a booking failure."""
        win = self._active_pair_window()
        if win is not None:
            win.set_status("FAILED", "#dc2626")
        self._show_booking_error(win, reason)

    def _on_booking_cancelled(self) -> None:
        """Handle a booking cancellation."""
        win = self._active_pair_window()
        if win is not None:
            win.set_status("CANCELLED", "#dc2626")

    def _show_booking_error(self, win: Optional[QWidget], message: str) -> None:
        parent = win or self._main_window
        if parent is not None:
            QMessageBox.warning(parent, "Booking Error", message)

    # ------------------------------------------------------------------
    # User-driven checkpoint dialogs (overridable for tests)
    # ------------------------------------------------------------------

    def _show_two_factor_dialog(self, win: Optional[QWidget]) -> Optional[str]:
        """Show the manual 2FA/OTP dialog; returns the code or None."""
        dlg = TwoFactorDialog(win)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.get_otp_code()
        return None

    def _show_captcha_dialog(self, win: Optional[QWidget]) -> Optional[str]:
        """Show the manual CAPTCHA dialog; returns the text or None."""
        dlg = CaptchaDialog(win)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.get_captcha_text()
        return None

    def _show_payment_details(self, win: Optional[QWidget]) -> None:
        """Display the selected bank/gateway and UPI / IPAYQR payment instructions."""
        bank = ""
        if win is not None:
            bank = win.bank_combo.currentText() or ""
        if not bank:
            bank = "IPPAYUPI · ipay@upi"
        parent = win or self._main_window
        if parent is None:
            return
        QMessageBox.information(
            parent,
            "Payment Handoff",
            "Complete payment manually in the opened IRCTC browser window.\n\n"
            f"Selected Gateway/Bank: {bank}\n"
            "UPI ID: ipay@upi\n"
            "IPAYQR: scan the QR shown on the payment page, or pay via any UPI app.\n\n"
            "Once the payment is approved, enter the PNR below to complete the booking.",
        )

    def _show_fare_confirm_dialog(self, win: Optional[QWidget]) -> bool:
        """Show the fare confirmation dialog; returns True if accepted."""
        session = self._booking_service.session if self._booking_service else None
        dlg = FareConfirmDialog(
            win,
            fare_amount=(session or {}).get("fare_amount"),
            train_number=(session or {}).get("train_number"),
            journey_date=(session or {}).get("journey_date"),
        )
        return dlg.exec() == QDialog.DialogCode.Accepted

    def _render_and_save_ers(self, pnr: str) -> str:
        """Render the ERS HTML for the completed booking and save it to disk."""
        if self._ticket_render_service is None or self._booking_service is None:
            return ""
        session = self._booking_service.session or {}
        ticket_id = session.get("ticket_id")
        ticket = None
        if ticket_id and self._ticket_service is not None:
            try:
                ticket = self._ticket_service.get_ticket(ticket_id)
            except Exception:
                ticket = None

        fare = session.get("fare_amount")
        passengers = []
        if ticket is not None:
            try:
                passengers = json.loads(ticket.get("passenger_details", "[]") or "[]")
            except Exception:
                passengers = []

        dto = {
            "HtmlTitle": "Electronic Reservation Slip",
            "bookingResponseDTO": {
                "pnrNumber": pnr,
                "trainNumber": ticket.get("train_number", "") if ticket else "",
                "trainName": "",
                "journeyClass": ticket.get("class", "") if ticket else "",
                "bookedQuota": ticket.get("quota", "") if ticket else "",
                "journeyQuota": ticket.get("quota", "") if ticket else "",
                "distance": "",
                "bookingDate": "",
                "fromStnName": ticket.get("from_station", "") if ticket else "",
                "fromStn": ticket.get("from_station", "") if ticket else "",
                "boardingStnName": ticket.get("from_station", "") if ticket else "",
                "boardingStn": ticket.get("from_station", "") if ticket else "",
                "resvnUptoStnName": ticket.get("to_station", "") if ticket else "",
                "resvnUptoStn": ticket.get("to_station", "") if ticket else "",
                "journeyDate": ticket.get("journey_date", "") if ticket else "",
                "boardingDate": ticket.get("journey_date", "") if ticket else "",
                "destArrvDate": ticket.get("journey_date", "") if ticket else "",
                "totalFare": str(fare) if fare is not None else "",
                "serviceChargeTotal": "",
            },
            "FullClassName": f"{ticket.get('class', '')} ({ticket.get('class', '')})" if ticket else "",
            "transactionId": f"TXN-{pnr}",
            "totalCollectibleAmount": str(fare) if fare is not None else "",
            "qrbase64String": "",
            "placeOfSupply": "NA",
            "stateNameCode": "Delhi/DL",
            "passengers": [
                {
                    "name": p.get("name", ""),
                    "age": p.get("age", ""),
                    "gender": p.get("gender", ""),
                    "booking_status": "CNF",
                    "current_status": "CNF",
                }
                for p in passengers if isinstance(p, dict)
            ],
        }

        html = self._ticket_render_service.render_html(dto)
        os.makedirs(self._ers_output_dir, exist_ok=True)
        out_path = os.path.join(self._ers_output_dir, f"ERS_{pnr}.html")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        return out_path

    def _on_launch_all_tickets(self) -> None:
        if self._ticket_service is None:
            return
        tickets = self._ticket_service.list_tickets()
        for idx, t in enumerate(tickets[:4]):  # open first few pairs
            self._on_open_ticket(t["id"], 0)

    def _on_edit_ticket(self, ticket_id: str) -> None:
        if self._ticket_service is None or self._book_window is None:
            return
        try:
            ticket = self._ticket_service.get_ticket(ticket_id)
        except Exception:
            return

        if self._account_service is not None:
            self._book_window.set_accounts(self._account_service.list_accounts())
        if self._proxy_service is not None:
            self._book_window.set_proxies(self._proxy_service.list_proxies())
        if self._payment_service is not None:
            self._book_window.set_payments(self._payment_service.list_methods())

        self._book_window.load_ticket(ticket)
        self._position_window_centered(self._book_window, top_offset=90)
        self._book_window.show()
        self._book_window.raise_()

    def _on_duplicate_ticket(self, ticket_id: str) -> None:
        if self._ticket_service is None:
            return
        try:
            t = self._ticket_service.get_ticket(ticket_id)
            self._ticket_service.add_ticket(
                train_number=t["train_number"],
                from_station=t["from_station"],
                to_station=t["to_station"],
                journey_date=t["journey_date"],
                class_type=t["class"],
                quota=t["quota"],
                passenger_details=t["passenger_details"],
                mobile=t.get("mobile"),
                email=t.get("email"),
                irctc_account_id=t.get("irctc_account_id"),
            )
            self._refresh_tickets_window()
        except Exception as e:
            if self._tickets_window is not None:
                QMessageBox.warning(self._tickets_window, "Duplicate Ticket", str(e))

    def _on_delete_ticket(self, ticket_id: str) -> None:
        if self._ticket_service is None:
            return
        try:
            self._ticket_service.delete_ticket(ticket_id)
            self._refresh_tickets_window()
        except Exception as e:
            if self._tickets_window is not None:
                QMessageBox.warning(self._tickets_window, "Delete Ticket", str(e))

    def _on_delete_all_tickets(self) -> None:
        if self._ticket_service is None:
            return
        for t in self._ticket_service.list_tickets():
            try:
                self._ticket_service.delete_ticket(t["id"])
            except Exception:
                pass
        self._refresh_tickets_window()

    # ------------------------------------------------------------------
    # Accounts & Payments & Proxies Handlers
    # ------------------------------------------------------------------

    def _on_add_account(self, data: dict) -> None:
        if self._account_service is None or self._accounts_window is None:
            return
        try:
            self._account_service.add_account(
                username=data["username"],
                password=data["password"],
                mobile=data.get("mobile"),
                email=data.get("email"),
            )
            self._accounts_window.set_accounts(self._account_service.list_accounts())
            self._accounts_window.show_toast(f"Added {data['username']}")
        except Exception as ex:
            QMessageBox.warning(self._accounts_window, "Account Error", str(ex))

    def _on_bulk_import_accounts(self, items: list[dict]) -> None:
        if self._account_service is None or self._accounts_window is None:
            return
        added = 0
        for it in items:
            try:
                self._account_service.add_account(
                    username=it["username"],
                    password=it["password"],
                    mobile=it.get("mobile"),
                    email=it.get("email"),
                )
                added += 1
            except Exception:
                pass
        self._accounts_window.set_accounts(self._account_service.list_accounts())
        self._accounts_window.show_toast(f"Imported {added} accounts")

    def _on_delete_account(self, account_id: str) -> None:
        if self._account_service is None or self._accounts_window is None:
            return
        try:
            self._account_service.delete_account(account_id)
            self._accounts_window.set_accounts(self._account_service.list_accounts())
        except Exception as ex:
            QMessageBox.warning(self._accounts_window, "Delete Account", str(ex))

    def _on_toggle_account_active(self, account_id: str, is_active: bool) -> None:
        if self._account_service is None or self._accounts_window is None:
            return
        try:
            self._account_service.update_account(account_id, is_active=is_active)
        except Exception as ex:
            QMessageBox.warning(self._accounts_window, "Update Account", str(ex))

    def _on_add_payment(self, data: dict) -> None:
        if self._payment_service is None or self._payment_window is None:
            return
        try:
            self._payment_service.add_method(
                method_type=data.get("type", "UPI"),
                gateway=data.get("gateway", ""),
                identifier=data.get("identifier", ""),
            )
            self._payment_window.set_payments(self._payment_service.list_methods())
        except Exception as ex:
            QMessageBox.warning(self._payment_window, "Payment Error", str(ex))

    def _on_delete_payment(self, payment_id: str) -> None:
        if self._payment_service is None or self._payment_window is None:
            return
        try:
            self._payment_service.delete_method(payment_id)
            self._payment_window.set_payments(self._payment_service.list_methods())
        except Exception as ex:
            QMessageBox.warning(self._payment_window, "Payment Error", str(ex))

    def _on_add_proxy(self, data: dict) -> None:
        if self._proxy_service is None or self._proxies_window is None:
            return
        try:
            self._proxy_service.add_proxy(
                host=data["host"],
                port=int(data["port"]),
                username=data.get("username"),
                password=data.get("password"),
            )
            self._proxies_window.set_proxies(self._proxy_service.list_proxies())
        except Exception as ex:
            QMessageBox.warning(self._proxies_window, "Proxy Error", str(ex))

    def _on_delete_proxy(self, proxy_id: str) -> None:
        if self._proxy_service is None or self._proxies_window is None:
            return
        try:
            self._proxy_service.delete_proxy(proxy_id)
            self._proxies_window.set_proxies(self._proxy_service.list_proxies())
        except Exception as ex:
            QMessageBox.warning(self._proxies_window, "Proxy Error", str(ex))

    def _on_test_proxy(self, proxy_id: str) -> None:
        if self._proxy_service is None or self._proxies_window is None:
            return
        try:
            self._proxy_service.test_proxy(proxy_id)
            self._proxies_window.set_proxies(self._proxy_service.list_proxies())
        except Exception as ex:
            QMessageBox.warning(self._proxies_window, "Test Proxy", str(ex))

    def _on_export_backup(self, file_path: str, pwd: str) -> None:
        if self._transfer_service is None or self._backup_restore_window is None:
            return
        try:
            self._transfer_service.export_backup(file_path, pwd)
            QMessageBox.information(
                self._backup_restore_window,
                "Backup Successful",
                f"Data successfully exported to:\n{file_path}",
            )
        except Exception as ex:
            QMessageBox.warning(self._backup_restore_window, "Backup Error", str(ex))

    def _on_import_backup(self, file_path: str, pwd: str, mode: str) -> None:
        if (
            self._transfer_service is None
            or self._backup_restore_window is None
            or self._account_service is None
            or self._proxy_service is None
        ):
            return
        try:
            self._transfer_service.import_backup(file_path, pwd, mode=mode)
            QMessageBox.information(
                self._backup_restore_window,
                "Restore Successful",
                "Backup data imported successfully.",
            )
            self._refresh_tickets_window()
            if self._accounts_window is not None:
                self._accounts_window.set_accounts(self._account_service.list_accounts())
            if self._proxies_window is not None:
                self._proxies_window.set_proxies(self._proxy_service.list_proxies())
        except Exception as ex:
            QMessageBox.warning(self._backup_restore_window, "Restore Error", str(ex))

    def _ensure_vault_window(self) -> None:
        """Create and wire the VaultWindow gate if it does not exist."""
        if self._vault_window is not None:
            return
        self._vault_window = VaultWindow()
        self._vault_window.set_vault(self._vault)
        self._vault_window.unlocked.connect(self._on_vault_unlocked)
        self._vault_window.quit_requested.connect(self.shutdown)
        if self._vault is not None:
            mode = "setup" if not self._vault.is_configured() else "unlock"
            self._vault_window.set_mode(mode)

    def _on_vault_unlocked(self) -> None:
        """Reveal the dock toolbar once the vault is unlocked."""
        if self._vault_window is not None:
            self._vault_window.hide()
        if self._main_window is None:
            self.create_main_window()
        if self._main_window is not None:
            self._main_window.show()
            self._main_window.raise_()

    # ------------------------------------------------------------------
    # Application Lifecycle
    # ------------------------------------------------------------------

    def run(self) -> int:
        """Run the application main loop.

        Returns the application exit code.
        """
        self.ready.emit()
        if self._vault is not None and not self._vault.is_unlocked():
            self._ensure_vault_window()
            self._vault_window.show()
            self._vault_window.raise_()
        elif self._main_window is not None:
            self._main_window.show()

        app = QApplication.instance()
        exit_code = 0
        if app is not None:
            exit_code = app.exec()
        self.shutdown()
        return exit_code

    def shutdown(self) -> None:
        """Signal that the application is shutting down and close all windows."""
        self.shutting_down.emit()
        for w in [
            self._main_window,
            self._book_window,
            self._tickets_window,
            self._train_results_window,
            self._tokens_window,
            self._accounts_window,
            self._payment_window,
            self._settings_window,
            self._proxies_window,
            self._history_window,
            self._backup_restore_window,
            self._vault_window,
        ]:
            if w is not None:
                try:
                    w.close()
                    w.deleteLater()
                except Exception:
                    pass
        for pw in list(self._pair_windows.values()):
            try:
                pw.close()
                pw.deleteLater()
            except Exception:
                pass
        self._pair_windows.clear()
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None

        app = QApplication.instance()
        if app is not None:
            try:
                app.quit()
            except Exception:
                pass
