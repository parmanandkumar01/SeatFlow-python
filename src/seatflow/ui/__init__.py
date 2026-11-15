"""UI package for SeatFlow."""

from seatflow.ui.accounts_window import AccountsWindow
from seatflow.ui.app_icon import apply_bingo_icon, bingo_logo_pixmap
from seatflow.ui.backup_restore_window import BackupRestoreWindow
from seatflow.ui.book_window import BookWindow
from seatflow.ui.history_window import HistoryWindow
from seatflow.ui.license_window import LicenseWindow
from seatflow.ui.main_window import MainToolbarWindow, MainWindow, place_toolbar_top
from seatflow.ui.payment_window import PaymentWindow
from seatflow.ui.proxies_window import ProxiesWindow
from seatflow.ui.settings_window import SettingsWindow
from seatflow.ui.ticket_panel_window import TicketPanelWindow
from seatflow.ui.tickets_window import TicketsWindow
from seatflow.ui.tokens_window import TokensWindow
from seatflow.ui.train_results_window import TrainResultsWindow
from seatflow.ui.update_window import UpdateWindow
from seatflow.ui.vault_window import VaultWindow
from seatflow.ui.window_drag import enable_window_drag

__all__ = [
    "AccountsWindow",
    "BackupRestoreWindow",
    "BookWindow",
    "HistoryWindow",
    "LicenseWindow",
    "MainToolbarWindow",
    "MainWindow",
    "PaymentWindow",
    "ProxiesWindow",
    "SettingsWindow",
    "TicketPanelWindow",
    "TicketsWindow",
    "TokensWindow",
    "TrainResultsWindow",
    "UpdateWindow",
    "VaultWindow",
    "apply_bingo_icon",
    "bingo_logo_pixmap",
    "enable_window_drag",
    "place_toolbar_top",
]
