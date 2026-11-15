"""Dialogs package."""

from seatflow.ui.dialogs.account_dialog import AccountDialog
from seatflow.ui.dialogs.booking_monitor_dialog import BookingMonitorDialog
from seatflow.ui.dialogs.captcha_dialog import CaptchaDialog
from seatflow.ui.dialogs.fare_confirm_dialog import FareConfirmDialog
from seatflow.ui.dialogs.news_dialog import NewsDialog
from seatflow.ui.dialogs.payment_dialog import PaymentDialog
from seatflow.ui.dialogs.proxy_dialog import ProxyDialog
from seatflow.ui.dialogs.ticket_dialog import TicketDialog
from seatflow.ui.dialogs.transfer_dialog import TransferDialog
from seatflow.ui.dialogs.two_factor_dialog import TwoFactorDialog

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