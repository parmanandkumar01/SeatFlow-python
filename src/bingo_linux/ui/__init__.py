"""UI package for Bingo Linux."""

from bingo_linux.ui.accounts_window import AccountsWindow
from bingo_linux.ui.app_icon import apply_bingo_icon, bingo_logo_pixmap
from bingo_linux.ui.backup_restore_window import BackupRestoreWindow
from bingo_linux.ui.book_window import BookWindow
from bingo_linux.ui.history_window import HistoryWindow
from bingo_linux.ui.main_window import MainToolbarWindow, MainWindow, place_toolbar_top
from bingo_linux.ui.payment_window import PaymentWindow
from bingo_linux.ui.proxies_window import ProxiesWindow
from bingo_linux.ui.settings_window import SettingsWindow
from bingo_linux.ui.ticket_panel_window import TicketPanelWindow
from bingo_linux.ui.tickets_window import TicketsWindow
from bingo_linux.ui.tokens_window import TokensWindow
from bingo_linux.ui.train_results_window import TrainResultsWindow
from bingo_linux.ui.update_window import UpdateWindow
from bingo_linux.ui.vault_window import VaultWindow
from bingo_linux.ui.window_drag import enable_window_drag

__all__ = [
    "AccountsWindow",
    "BackupRestoreWindow",
    "BookWindow",
    "HistoryWindow",
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
