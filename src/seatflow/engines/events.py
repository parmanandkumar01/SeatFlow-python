"""Standard event models emitted by engines and consumed by the UI and runner."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EngineEventType(str, Enum):
    """Categorized types of engine events."""
    STATUS_CHANGED = "status_changed"
    STEP_PROGRESS = "step_progress"
    CAPTCHA_REQUESTED = "captcha_requested"
    TWO_FACTOR_REQUESTED = "two_factor_requested"
    PAYMENT_REQUESTED = "payment_requested"
    BOOKING_COMPLETED = "booking_completed"
    ERROR = "error"
    LOG = "log"


@dataclass
class EngineEvent:
    """Base event model."""
    engine_id: str
    event_type: EngineEventType
    timestamp: float = field(default_factory=time.time)


@dataclass
class StatusChangedEvent(EngineEvent):
    """Fired when an engine transitions between states."""
    old_status: str = ""
    new_status: str = ""
    message: str = ""

    def __init__(self, engine_id: str, old_status: str, new_status: str, message: str = ""):
        super().__init__(engine_id=engine_id, event_type=EngineEventType.STATUS_CHANGED)
        self.old_status = old_status
        self.new_status = new_status
        self.message = message


@dataclass
class StepProgressEvent(EngineEvent):
    """Fired as the engine executes individual steps."""
    step_name: str = ""
    current_step: int = 0
    total_steps: int = 0
    description: str = ""
    elapsed_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        engine_id: str,
        step_name: str,
        current_step: int,
        total_steps: int,
        description: str = "",
        elapsed_ms: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(engine_id=engine_id, event_type=EngineEventType.STEP_PROGRESS)
        self.step_name = step_name
        self.current_step = current_step
        self.total_steps = total_steps
        self.description = description
        self.elapsed_ms = elapsed_ms
        self.metadata = metadata or {}


@dataclass
class CaptchaRequestedEvent(EngineEvent):
    """Fired when manual or external CAPTCHA input is required."""
    captcha_id: str = ""
    image_base64: str = ""
    prompt_text: str = "Please enter the CAPTCHA code shown"

    def __init__(self, engine_id: str, captcha_id: str, image_base64: str, prompt_text: str = ""):
        super().__init__(engine_id=engine_id, event_type=EngineEventType.CAPTCHA_REQUESTED)
        self.captcha_id = captcha_id
        self.image_base64 = image_base64
        if prompt_text:
            self.prompt_text = prompt_text


@dataclass
class TwoFactorRequestedEvent(EngineEvent):
    """Fired when 2FA / OTP verification is required."""
    transaction_id: str = ""
    mobile_mask: str = ""
    otp_type: str = "LOGIN"  # LOGIN, BOOKING, PAYMENT

    def __init__(self, engine_id: str, transaction_id: str = "", mobile_mask: str = "", otp_type: str = "LOGIN"):
        super().__init__(engine_id=engine_id, event_type=EngineEventType.TWO_FACTOR_REQUESTED)
        self.transaction_id = transaction_id
        self.mobile_mask = mobile_mask
        self.otp_type = otp_type


@dataclass
class PaymentRequestedEvent(EngineEvent):
    """Fired when checkout is ready and payment handoff is required."""
    amount: float = 0.0
    payment_options: List[str] = field(default_factory=list)
    qr_data: str = ""
    instructions: str = ""

    def __init__(
        self,
        engine_id: str,
        amount: float = 0.0,
        payment_options: Optional[List[str]] = None,
        qr_data: str = "",
        instructions: str = "",
    ):
        super().__init__(engine_id=engine_id, event_type=EngineEventType.PAYMENT_REQUESTED)
        self.amount = amount
        self.payment_options = payment_options or ["UPI", "NET_BANKING", "CREDIT_CARD"]
        self.qr_data = qr_data
        self.instructions = instructions


@dataclass
class BookingCompletedEvent(EngineEvent):
    """Fired upon successful ticket booking."""
    pnr: str = ""
    train_number: str = ""
    booking_status: str = "CONFIRMED"
    fare_paid: float = 0.0
    ers_html: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        engine_id: str,
        pnr: str,
        train_number: str = "",
        booking_status: str = "CONFIRMED",
        fare_paid: float = 0.0,
        ers_html: str = "",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(engine_id=engine_id, event_type=EngineEventType.BOOKING_COMPLETED)
        self.pnr = pnr
        self.train_number = train_number
        self.booking_status = booking_status
        self.fare_paid = fare_paid
        self.ers_html = ers_html
        self.details = details or {}


@dataclass
class EngineErrorEvent(EngineEvent):
    """Fired when an unrecoverable or recoverable engine error occurs."""
    error_code: str = ""
    message: str = ""
    recoverable: bool = False

    def __init__(self, engine_id: str, error_code: str, message: str, recoverable: bool = False):
        super().__init__(engine_id=engine_id, event_type=EngineEventType.ERROR)
        self.error_code = error_code
        self.message = message
        self.recoverable = recoverable
