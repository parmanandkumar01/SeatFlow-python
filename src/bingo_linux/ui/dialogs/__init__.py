"""Dialogs package."""

from bingo_linux.ui.dialogs.account_dialog import AccountDialog
from bingo_linux.ui.dialogs.booking_monitor_dialog import BookingMonitorDialog
from bingo_linux.ui.dialogs.captcha_dialog import CaptchaDialog
from bingo_linux.ui.dialogs.fare_confirm_dialog import FareConfirmDialog
from bingo_linux.ui.dialogs.news_dialog import NewsDialog
from bingo_linux.ui.dialogs.payment_dialog import PaymentDialog
from bingo_linux.ui.dialogs.proxy_dialog import ProxyDialog
from bingo_linux.ui.dialogs.ticket_dialog import TicketDialog
from bingo_linux.ui.dialogs.transfer_dialog import TransferDialog
from bingo_linux.ui.dialogs.two_factor_dialog import TwoFactorDialog

__all__ = [
    "AccountDialog",
    "BookingMonitorDialog",
    "CaptchaDialog",
    "FareConfirmDialog",
    "NewsDialog",
    "PaymentDialog",
    "ProxyDialog",
    "TicketDialog",
    "TransferDialog",
    "TwoFactorDialog",
]