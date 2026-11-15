"""Chrome Native Messaging host for the Browser Extension Bridge.

Exchanges length-prefixed JSON envelopes with a companion Chrome/Chromium
extension over stdin/stdout. The host performs zero network I/O; all
navigation happens in the user's visible browser. Messages carry UI context
only -- never credentials, card numbers, CVVs, PINs, or OTPs.

Envelope (see architecture/ipc_message_protocol.md):
{
  "msg_id": "<uuid>",
  "ts": "<ISO-8601 UTC>",
  "direction": "app->ext | ext->app",
  "type": "<message type>",
  "payload": { ... },
  "session_id": "<optional booking session uuid>"
}
"""

from __future__ import annotations

import json
import struct
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

MESSAGE_TYPES = frozenset({
    "open_booking",
    "form_context",
    "captcha_detected",
    "otp_prompt",
    "payment_page",
    "pnr_received",
    "ack",
    "error",
})

DIRECTIONS = frozenset({"app->ext", "ext->app"})

SENSITIVE_PAYLOAD_KEYS = frozenset({
    "username", "password", "card_number", "cvv", "pin", "otp",
    "session_id_irctc", "token", "cookie",
})

_HEADER_STRUCT = struct.Struct("<I")


class NativeHostError(Exception):
    """Raised for native host protocol errors."""


class InvalidEnvelopeError(NativeHostError):
    """Raised when a message envelope fails validation."""


class BridgeDisabledError(NativeHostError):
    """Raised when the bridge is disabled and a message cannot be routed."""


class NativeHost:
    """Native-messaging host core: framing, validation, and routing.

    The host is transport-agnostic: it exposes read_message and write_message
    for stdio, and route for dispatching a validated envelope to a
    caller-supplied router. It performs no network I/O itself.
    """

    def __init__(
        self,
        allowed_origin: Optional[str] = None,
        router: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    ) -> None:
        self._allowed_origin = allowed_origin
        self._router = router
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def read_message(self) -> Optional[dict[str, Any]]:
        raw_len = sys.stdin.buffer.read(4)
        if not raw_len:
            return None
        if len(raw_len) < 4:
            raise NativeHostError("Incomplete message length header")
        (length,) = _HEADER_STRUCT.unpack(raw_len)
        if length <= 0 or length > 16 * 1024 * 1024:
            raise NativeHostError(f"Invalid message length: {length}")
        raw_body = sys.stdin.buffer.read(length)
        if len(raw_body) < length:
            raise NativeHostError("Incomplete message body")
        try:
            return json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise NativeHostError(f"Invalid JSON message: {exc}") from exc

    def write_message(self, message: dict[str, Any]) -> None:
        body = json.dumps(message, separators=(",", ":")).encode("utf-8")
        sys.stdout.buffer.write(_HEADER_STRUCT.pack(len(body)))
        sys.stdout.buffer.write(body)
        sys.stdout.buffer.flush()

    def validate_envelope(self, envelope: Any) -> dict[str, Any]:
        if not isinstance(envelope, dict):
            raise InvalidEnvelopeError("Envelope must be a JSON object")

        msg_id = envelope.get("msg_id")
        ts = envelope.get("ts")
        direction = envelope.get("direction")
        msg_type = envelope.get("type")
        payload = envelope.get("payload")
        session_id = envelope.get("session_id")

        if not isinstance(msg_id, str) or not msg_id:
            raise InvalidEnvelopeError("msg_id is required and must be a non-empty string")
        try:
            uuid.UUID(msg_id)
        except (ValueError, AttributeError):
            raise InvalidEnvelopeError("msg_id must be a valid UUID")

        if not isinstance(ts, str) or not ts:
            raise InvalidEnvelopeError("ts is required and must be a non-empty string")
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            raise InvalidEnvelopeError("ts must be a valid ISO-8601 timestamp")

        if direction not in DIRECTIONS:
            raise InvalidEnvelopeError(
                f"direction must be one of: {', '.join(sorted(DIRECTIONS))}"
            )

        if msg_type not in MESSAGE_TYPES:
            raise InvalidEnvelopeError(
                f"type must be one of: {', '.join(sorted(MESSAGE_TYPES))}"
            )

        if not isinstance(payload, dict):
            raise InvalidEnvelopeError("payload must be a JSON object")

        if session_id is not None and not isinstance(session_id, str):
            raise InvalidEnvelopeError("session_id must be a string when present")

        self._check_sensitive_keys(payload)

        return envelope

    def _check_sensitive_keys(self, payload: dict[str, Any], path: str = "payload") -> None:
        for key, value in payload.items():
            if key.lower() in SENSITIVE_PAYLOAD_KEYS:
                raise InvalidEnvelopeError(
                    f"Sensitive key {key!r} is not allowed in {path}"
                )
            if isinstance(value, dict):
                self._check_sensitive_keys(value, f"{path}.{key}")

    def route(self, envelope: dict[str, Any]) -> dict[str, Any]:
        if not self._enabled:
            raise BridgeDisabledError("Bridge is disabled")
        if envelope.get("direction") != "ext->app":
            raise InvalidEnvelopeError("route() expects an ext->app envelope")

        if self._router is None:
            return self._ack(envelope, "ok", "No router configured")

        try:
            result = self._router(envelope)
            if not isinstance(result, dict):
                result = {}
            return self._ack(envelope, "ok", "", extra=result)
        except InvalidEnvelopeError as exc:
            return self._error(envelope, "invalid_envelope", str(exc))
        except BridgeDisabledError as exc:
            return self._error(envelope, "bridge_disabled", str(exc))
        except Exception as exc:
            return self._error(envelope, "internal_error", str(exc))

    def make_outbound(
        self,
        msg_type: str,
        payload: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if msg_type not in MESSAGE_TYPES:
            raise InvalidEnvelopeError(f"Unknown message type: {msg_type!r}")
        return {
            "msg_id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "direction": "app->ext",
            "type": msg_type,
            "payload": payload or {},
            "session_id": session_id,
        }

    def run_stdio(self) -> None:
        while True:
            try:
                envelope = self.read_message()
            except NativeHostError:
                break
            if envelope is None:
                break
            try:
                self.validate_envelope(envelope)
            except InvalidEnvelopeError as exc:
                self.write_message(self._error_from_raw(envelope, "invalid_envelope", str(exc)))
                continue
            if envelope.get("direction") == "ext->app":
                try:
                    response = self.route(envelope)
                except BridgeDisabledError:
                    response = self._error_from_raw(
                        envelope, "bridge_disabled", "Bridge is disabled"
                    )
                self.write_message(response)

    @staticmethod
    def _ack(
        envelope: dict[str, Any],
        status: str,
        message: str = "",
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ack_msg_id": envelope.get("msg_id", ""),
            "status": status,
        }
        if message:
            payload["message"] = message
        if extra:
            payload.update(extra)
        return {
            "msg_id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "direction": "app->ext",
            "type": "ack",
            "payload": payload,
            "session_id": envelope.get("session_id"),
        }

    @staticmethod
    def _error(
        envelope: dict[str, Any],
        code: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "msg_id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "direction": "app->ext",
            "type": "error",
            "payload": {"code": code, "message": message},
            "session_id": envelope.get("session_id"),
        }

    @staticmethod
    def _error_from_raw(
        envelope: Any,
        code: str,
        message: str,
    ) -> dict[str, Any]:
        session_id = envelope.get("session_id") if isinstance(envelope, dict) else None
        return {
            "msg_id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "direction": "app->ext",
            "type": "error",
            "payload": {"code": code, "message": message},
            "session_id": session_id,
        }


def main() -> None:
    host = NativeHost()
    host.run_stdio()


if __name__ == "__main__":
    main()
