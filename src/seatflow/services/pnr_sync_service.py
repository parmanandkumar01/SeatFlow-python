"""Live CRIS PNR Sync service (RT-06).

Read-only, user-initiated PNR status lookup against a user-configured
endpoint. Implements the documented integration interface:

- Single PNR lookup per request (no bulk enumeration).
- Client-side rate-limit cooldown (default 60s per PNR).
- User-configurable endpoint URL (empty by default: live refresh is
  blocked until the endpoint contract is recovered).
- No IRCTC credentials; PNR number only.
- Stops and surfaces "manual verification required" on CAPTCHA / bot
  challenge; backs off on 429 / rate-limit.
- Offline graceful: returns the last-cached status with an offline flag.
- Persists refreshed status + looked_up_at to `pnr_records`.
- Detects status change vs. the previously stored value.

This service does NOT hardcode a live PNR endpoint: the erail.in PNR
mirror contract (URL + response schema) is not recovered, so live
refresh is unavailable until the contract is authenticated.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

from PySide6.QtCore import QObject, Signal

from seatflow.services.pnr_service import (
    PNR_STATUS_BOOKED,
    PNR_STATUS_CANCELLED,
    PNR_STATUS_FAILED,
    PNR_STATUS_PENDING,
    PnrService,
    PnrServiceError,
)

try:
    import httpx  # type: ignore

    _HAVE_HTTPX = True
except ImportError:  # pragma: no cover - optional dependency
    _HAVE_HTTPX = False

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Status values returned by railway PNR endpoints that map to the app's
# canonical booking statuses.
_CNF = frozenset({"cnf", "confirmed", "booked", "chart prepared", "chart_prepared"})
_RAC = frozenset({"rac"})
_WAITLIST = frozenset({"wl", "waitlist", "waiting"})
_CANCELLED = frozenset({"cancelled", "cancelled_"})
_FAILED = frozenset({"failed", "error", "not_found", "invalid"})

DEFAULT_COOLDOWN_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 15.0


class PnrSyncError(Exception):
    """Raised for PNR sync lifecycle errors."""


class PnrSyncService(QObject):
    """Read-only, user-initiated PNR status refresh service."""

    #: Emitted when a PNR is refreshed: (pnr_number, result_dict).
    pnr_refreshed = Signal(str, dict)
    #: Emitted on error: (pnr_number, message).
    pnr_error = Signal(str, str)
    #: Emitted when a lookup is in cooldown: (pnr_number, remaining_seconds).
    cooldown_active = Signal(str, int)

    def __init__(
        self,
        settings_service,
        pnr_service: PnrService,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings_service
        self._pnr_service = pnr_service
        # Per-PNR last-lookup timestamps for client-side cooldown.
        self._last_lookup: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @property
    def endpoint_url(self) -> str:
        return self._settings.get_pnr_endpoint_url()

    @property
    def cooldown_seconds(self) -> int:
        return self._settings.get_pnr_cooldown_seconds()

    def set_endpoint_url(self, url: str) -> None:
        self._settings.set_pnr_endpoint_url(url)

    def set_cooldown_seconds(self, cooldown: int) -> None:
        self._settings.set_pnr_cooldown_seconds(cooldown)

    def is_endpoint_configured(self) -> bool:
        return bool(self.endpoint_url.strip())

    # ------------------------------------------------------------------
    # Public API: user-initiated single PNR refresh
    # ------------------------------------------------------------------

    def refresh_pnr(self, pnr_number: str) -> dict[str, Any]:
        """Refresh the status of a single PNR on user demand.

        Returns a result dict with keys:
          ok, pnr_number, status, train_number, journey_date,
          travel_class, fare_amount, chart_status, looked_up_at,
          source, offline, cooldown_remaining, endpoint_not_configured,
          manual_verification_required, status_changed, previous_status.
        """
        pnr_clean = (pnr_number or "").strip()
        if not pnr_clean:
            result = self._result(
                pnr_number="",
                ok=False,
                error="pnr_required",
                message="PNR number is required.",
            )
            self.pnr_error.emit("", result.get("message", ""))
            return result

        if not pnr_clean.isalnum() or len(pnr_clean) < 6 or len(pnr_clean) > 20:
            result = self._result(
                pnr_number=pnr_clean,
                ok=False,
                error="invalid_pnr",
                message="PNR number must be alphanumeric and 6-20 characters.",
            )
            self.pnr_error.emit(pnr_clean, result.get("message", ""))
            return result

        # Endpoint not configured: live refresh is blocked (contract not
        # recovered). Do not invent or guess a URL.
        if not self.is_endpoint_configured():
            result = self._result(
                pnr_number=pnr_clean,
                ok=False,
                error="endpoint_not_configured",
                message=(
                    "Live PNR endpoint is not configured. "
                    "Configure the PNR status endpoint URL in Settings, "
                    "or the endpoint contract must be recovered before "
                    "live refresh is available."
                ),
                endpoint_not_configured=True,
            )
            self.pnr_error.emit(pnr_clean, result.get("message", ""))
            return result

        # Client-side cooldown (MW-06 / PNR-06).
        cooldown = self.cooldown_seconds
        now = time.time()
        last = self._last_lookup.get(pnr_clean)
        if last is not None and cooldown > 0:
            elapsed = now - last
            remaining = int(cooldown - elapsed)
            if remaining > 0:
                result = self._result(
                    pnr_number=pnr_clean,
                    ok=False,
                    error="cooldown",
                    message=f"Try again in {remaining} second(s).",
                    cooldown_remaining=remaining,
                )
                self.cooldown_active.emit(pnr_clean, remaining)
                self.pnr_error.emit(pnr_clean, result.get("message", ""))
                return result

        # Perform the lookup.
        try:
            response = self._perform_lookup(pnr_clean)
        except PnrSyncError as exc:
            # Network failure or bot challenge: show cached status.
            cached = self._pnr_service.get_pnr(pnr_clean) if self._pnr_service else None
            result = self._result(
                pnr_number=pnr_clean,
                ok=False,
                error="lookup_failed",
                message=str(exc),
                offline=True,
                cached=bool(cached),
                cached_status=(cached.get("booking_status") if cached else None),
            )
            self.pnr_error.emit(pnr_clean, str(exc))
            return result
        except Exception as exc:  # pragma: no cover - defensive
            result = self._result(
                pnr_number=pnr_clean,
                ok=False,
                error="lookup_failed",
                message=f"Unexpected error: {exc}",
                offline=True,
            )
            self.pnr_error.emit(pnr_clean, str(exc))
            return result

        # Bot challenge / CAPTCHA: stop, never automate through.
        if response.get("bot_challenge"):
            self._last_lookup[pnr_clean] = now
            result = self._result(
                pnr_number=pnr_clean,
                ok=False,
                error="bot_challenge",
                message=(
                    "The endpoint returned a CAPTCHA or bot-verification "
                    "challenge. Automatic PNR refresh is not supported; "
                    "please verify manually in the browser."
                ),
                manual_verification_required=True,
            )
            self.pnr_error.emit(pnr_clean, result.get("message", ""))
            return result

        # Rate-limit / 429: back off, respect cooldown.
        if response.get("rate_limited"):
            self._last_lookup[pnr_clean] = now
            remaining = int(response.get("retry_after", cooldown))
            result = self._result(
                pnr_number=pnr_clean,
                ok=False,
                error="rate_limited",
                message=f"Endpoint rate-limited. Try again in {remaining}s.",
                cooldown_remaining=remaining,
            )
            self.cooldown_active.emit(pnr_clean, remaining)
            self.pnr_error.emit(pnr_clean, result.get("message", ""))
            return result

        # Parse the response.
        parsed = self._parse_response(response.get("text", ""), pnr_clean)
        if parsed.get("error"):
            result = self._result(
                pnr_number=pnr_clean,
                ok=False,
                error=parsed["error"],
                message=parsed.get("message", "Failed to parse PNR response."),
                offline=True,
            )
            self.pnr_error.emit(pnr_clean, result.get("message", ""))
            return result

        # Record the lookup timestamp (cooldown).
        self._last_lookup[pnr_clean] = now

        # Persist to pnr_records.
        previous_status = None
        try:
            existing = self._pnr_service.get_pnr(pnr_clean)
            previous_status = existing.get("booking_status") if existing else None
        except Exception:
            existing = None

        new_status = self._normalize_status(parsed.get("status", ""))
        fare = parsed.get("fare_amount")
        try:
            if existing is None:
                self._pnr_service.add_pnr(
                    pnr_number=pnr_clean,
                    train_number=parsed.get("train_number"),
                    journey_date=parsed.get("journey_date"),
                    booking_status=new_status,
                    fare_amount=fare,
                )
            else:
                self._pnr_service.update_pnr(
                    pnr_number=pnr_clean,
                    booking_status=new_status,
                    train_number=(
                        parsed.get("train_number")
                        or existing.get("train_number")
                    ),
                    journey_date=(
                        parsed.get("journey_date")
                        or existing.get("journey_date")
                    ),
                    fare_amount=(
                        fare if fare is not None else existing.get("fare_amount")
                    ),
                    looked_up_at=datetime.now(timezone.utc).isoformat(),
                )
        except PnrServiceError as exc:
            result = self._result(
                pnr_number=pnr_clean,
                ok=False,
                error="persist_failed",
                message=f"Failed to persist PNR status: {exc}",
            )
            self.pnr_error.emit(pnr_clean, str(exc))
            return result

        status_changed = previous_status is not None and previous_status != new_status

        result = self._result(
            pnr_number=pnr_clean,
            ok=True,
            status=new_status,
            train_number=parsed.get("train_number"),
            journey_date=parsed.get("journey_date"),
            travel_class=parsed.get("travel_class"),
            fare_amount=fare,
            chart_status=parsed.get("chart_status"),
            looked_up_at=datetime.now(timezone.utc).isoformat(),
            source="endpoint",
            offline=False,
            status_changed=status_changed,
            previous_status=previous_status,
            message="PNR status refreshed.",
        )
        self.pnr_refreshed.emit(pnr_number, result)
        return result

    # ------------------------------------------------------------------
    # Network lookup (separated for testing / monkeypatching)
    # ------------------------------------------------------------------

    def _perform_lookup(self, pnr_number: str) -> dict[str, Any]:
        """Perform a single GET to the configured PNR endpoint.

        Returns a dict: {text, status_code, bot_challenge, rate_limited,
        retry_after}. Raises PnrSyncError on network failure.
        """
        url = self.endpoint_url.rstrip("/")
        params = urlencode({"pnr": pnr_number})
        full_url = f"{url}?{params}" if "?" not in url else f"{url}&{params}"
        headers = {
            "User-Agent": DEFAULT_UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.irctc.co.in/",
        }

        last_error: Optional[str] = None
        if _HAVE_HTTPX:
            try:
                import httpx

                with httpx.Client(
                    timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True
                ) as client:
                    res = client.get(full_url, headers=headers)
                    text = res.text or ""
                    status_code = res.status_code
                    if status_code == 429:
                        return {
                            "text": text,
                            "status_code": status_code,
                            "rate_limited": True,
                            "retry_after": int(
                                res.headers.get("retry-after", self.cooldown_seconds)
                            ),
                        }
                    if status_code in (403, 429) or self._looks_like_bot_challenge(text):
                        return {
                            "text": text,
                            "status_code": status_code,
                            "bot_challenge": True,
                        }
                    if status_code >= 400:
                        raise PnrSyncError(
                            f"Endpoint returned HTTP {status_code}"
                        )
                    return {"text": text, "status_code": status_code}
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_error = str(exc)
        else:
            try:
                req = urllib.request.Request(full_url, headers=headers)
                with urllib.request.urlopen(
                    req, timeout=REQUEST_TIMEOUT_SECONDS
                ) as resp:
                    text = resp.read().decode("utf-8", errors="replace")
                    status_code = resp.getcode()
                    if status_code >= 400:
                        raise PnrSyncError(
                            f"Endpoint returned HTTP {status_code}"
                        )
                    return {"text": text, "status_code": status_code}
            except (urllib.error.URLError, OSError) as exc:
                last_error = str(exc)

        raise PnrSyncError(last_error or "PNR lookup failed")

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_response(self, text: str, pnr_number: str) -> dict[str, Any]:
        """Parse a PNR endpoint response into normalized fields.

        Supports JSON responses with fields such as pnr/status/train/date/
        class/fare/chart_status. Returns a dict with an ``error`` key when
        the response cannot be parsed.
        """
        if not text or not text.strip():
            return {
                "error": "empty_response",
                "message": "The endpoint returned an empty response.",
            }

        stripped = text.strip()

        # JSON response.
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                return {
                    "error": "unparseable",
                    "message": "The endpoint response is not valid JSON.",
                }
            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict):
                return {
                    "error": "unparseable",
                    "message": "The endpoint response has an unexpected shape.",
                }
            # Bot-challenge markers sometimes appear in JSON.
            if str(data.get("captcha", "")).lower() in ("true", "1", "yes") or str(
                data.get("bot_protection", "")
            ).lower() in ("true", "1", "yes"):
                return {
                    "error": "bot_challenge",
                    "message": "The endpoint requires CAPTCHA verification.",
                }
            return {
                "status": self._first(
                    data,
                    "status", "booking_status", "pnr_status", "current_status",
                ),
                "train_number": self._first(
                    data, "train", "train_number", "train_no", "trainNumber"
                ),
                "journey_date": self._first(
                    data, "date", "journey_date", "travel_date"
                ),
                "travel_class": self._first(
                    data, "class", "travel_class", "coach_class"
                ),
                "fare_amount": self._parse_fare(
                    self._first(
                        data, "fare", "fare_amount", "amount", "price"
                    )
                ),
                "chart_status": self._first(
                    data, "chart_status", "chart", "coach_position"
                ),
            }

        # Non-JSON (HTML/text) response: cannot reliably parse without a
        # recovered contract. Refuse rather than guess.
        return {
            "error": "unparseable",
            "message": (
                "The endpoint returned a non-JSON response. The PNR endpoint "
                "contract (response schema) is not recovered, so live parsing "
                "is not implemented."
            ),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _first(obj: dict, *keys: str) -> Optional[str]:
        for key in keys:
            if key in obj and obj[key] is not None:
                value = str(obj[key]).strip()
                if value:
                    return value
        return None

    @staticmethod
    def _parse_fare(value: Optional[str]) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(str(value).replace(",", "").replace("₹", "").strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _looks_like_bot_challenge(text: str) -> bool:
        lowered = text.lower()
        indicators = ("captcha", "verify you are human", "bot detection",
                      "unusual traffic", "automated", "blocked")
        return any(ind in lowered for ind in indicators)

    @staticmethod
    def _normalize_status(status: Optional[str]) -> str:
        """Map a live endpoint status to a canonical booking status."""
        if not status:
            return PNR_STATUS_PENDING
        s = str(status).strip().lower()
        if s in _CNF:
            return PNR_STATUS_BOOKED
        if s in _RAC:
            return PNR_STATUS_PENDING
        if s in _WAITLIST:
            return PNR_STATUS_PENDING
        if s in _CANCELLED:
            return PNR_STATUS_CANCELLED
        if s in _FAILED:
            return PNR_STATUS_FAILED
        # Unknown status: preserve as-is but fall back to pending.
        return PNR_STATUS_PENDING

    def _result(self, **fields: Any) -> dict[str, Any]:
        base = {
            "ok": False,
            "pnr_number": "",
            "status": None,
            "train_number": None,
            "journey_date": None,
            "travel_class": None,
            "fare_amount": None,
            "chart_status": None,
            "looked_up_at": None,
            "source": None,
            "offline": False,
            "cooldown_remaining": None,
            "endpoint_not_configured": False,
            "manual_verification_required": False,
            "status_changed": False,
            "previous_status": None,
            "error": None,
            "message": "",
        }
        base.update(fields)
        return base
