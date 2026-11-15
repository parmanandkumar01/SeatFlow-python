"""Tests for the Chrome Native Messaging host (Browser Extension Bridge).

Covers:
- Envelope validation (valid and invalid envelopes)
- Sensitive key rejection in payloads
- Outbound envelope construction (make_outbound)
- Ack/error response construction
- Message routing (ext->app) via router callback
- Bridge disabled behavior
- Length-framed stdio read/write

No network I/O is performed; stdio is simulated with in-memory buffers.
"""

from __future__ import annotations

import io
import json
import struct
import sys
import uuid
import unittest
from unittest.mock import patch

from seatflow.integrations.native_host import (
    BridgeDisabledError,
    InvalidEnvelopeError,
    NativeHost,
    NativeHostError,
)


def valid_envelope(
    direction: str = "ext->app",
    msg_type: str = "pnr_received",
    payload: Optional[dict] = None,
    session_id: str = "sess_abc123",
) -> dict:
    return {
        "msg_id": str(uuid.uuid4()),
        "ts": "2026-11-15T06:36:00Z",
        "direction": direction,
        "type": msg_type,
        "payload": payload or {},
        "session_id": session_id,
    }


# Optional is only used in type hints below; import properly.
from typing import Optional  # noqa: E402


class NativeHostValidationTestCase(unittest.TestCase):
    """Tests for envelope validation."""

    def setUp(self) -> None:
        self.host = NativeHost()

    def test_valid_envelope_passes(self) -> None:
        env = valid_envelope()
        result = self.host.validate_envelope(env)
        self.assertIs(result, env)

    def test_valid_envelope_app_to_ext(self) -> None:
        env = valid_envelope(direction="app->ext", msg_type="open_booking")
        self.host.validate_envelope(env)

    def test_all_message_types_accepted(self) -> None:
        for msg_type in (
            "open_booking",
            "form_context",
            "captcha_detected",
            "otp_prompt",
            "payment_page",
            "pnr_received",
            "ack",
            "error",
        ):
            env = valid_envelope(msg_type=msg_type)
            self.host.validate_envelope(env)

    def test_non_dict_rejected(self) -> None:
        with self.assertRaises(InvalidEnvelopeError):
            self.host.validate_envelope("not a dict")

    def test_missing_msg_id_rejected(self) -> None:
        env = valid_envelope()
        del env["msg_id"]
        with self.assertRaises(InvalidEnvelopeError):
            self.host.validate_envelope(env)

    def test_invalid_uuid_msg_id_rejected(self) -> None:
        env = valid_envelope()
        env["msg_id"] = "not-a-uuid"
        with self.assertRaises(InvalidEnvelopeError):
            self.host.validate_envelope(env)

    def test_missing_ts_rejected(self) -> None:
        env = valid_envelope()
        del env["ts"]
        with self.assertRaises(InvalidEnvelopeError):
            self.host.validate_envelope(env)

    def test_invalid_ts_rejected(self) -> None:
        env = valid_envelope()
        env["ts"] = "not-a-timestamp"
        with self.assertRaises(InvalidEnvelopeError):
            self.host.validate_envelope(env)

    def test_invalid_direction_rejected(self) -> None:
        env = valid_envelope()
        env["direction"] = "in->out"
        with self.assertRaises(InvalidEnvelopeError):
            self.host.validate_envelope(env)

    def test_unknown_type_rejected(self) -> None:
        env = valid_envelope()
        env["type"] = "steal_credentials"
        with self.assertRaises(InvalidEnvelopeError):
            self.host.validate_envelope(env)

    def test_payload_not_dict_rejected(self) -> None:
        env = valid_envelope()
        env["payload"] = [1, 2, 3]
        with self.assertRaises(InvalidEnvelopeError):
            self.host.validate_envelope(env)


class NativeHostSensitiveKeyTestCase(unittest.TestCase):
    """Tests that sensitive keys are rejected from payloads."""

    def setUp(self) -> None:
        self.host = NativeHost()

    def test_sensitive_key_rejected(self) -> None:
        for key in (
            "username", "password", "card_number", "cvv", "pin", "otp",
            "token", "cookie",
        ):
            env = valid_envelope(payload={key: "secret"})
            with self.assertRaises(InvalidEnvelopeError):
                self.host.validate_envelope(env)

    def test_nested_sensitive_key_rejected(self) -> None:
        env = valid_envelope(payload={"inner": {"password": "secret"}})
        with self.assertRaises(InvalidEnvelopeError):
            self.host.validate_envelope(env)

    def test_safe_keys_accepted(self) -> None:
        env = valid_envelope(
            payload={
                "train_number": "12345",
                "pnr": "ABCD1234",
                "stage": "payment",
                "gateway": "UPI",
            }
        )
        self.host.validate_envelope(env)


class NativeHostOutboundTestCase(unittest.TestCase):
    """Tests for outbound envelope construction."""

    def setUp(self) -> None:
        self.host = NativeHost()

    def test_make_outbound_open_booking(self) -> None:
        env = self.host.make_outbound(
            "open_booking",
            payload={"url": "https://www.irctc.co.in/ntrain/train", "train_number": "12345"},
            session_id="sess_1",
        )
        self.assertEqual(env["direction"], "app->ext")
        self.assertEqual(env["type"], "open_booking")
        self.assertEqual(env["session_id"], "sess_1")
        self.assertEqual(env["payload"]["train_number"], "12345")
        self.assertIsInstance(env["msg_id"], str)
        self.assertIsInstance(env["ts"], str)

    def test_make_outbound_unknown_type_rejected(self) -> None:
        with self.assertRaises(InvalidEnvelopeError):
            self.host.make_outbound("steal_credentials")

    def test_make_outbound_default_payload(self) -> None:
        env = self.host.make_outbound("ack")
        self.assertEqual(env["payload"], {})


class NativeHostAckErrorTestCase(unittest.TestCase):
    """Tests for ack/error response construction."""

    def setUp(self) -> None:
        self.host = NativeHost()
        self.env = valid_envelope()

    def test_ack_structure(self) -> None:
        ack = self.host._ack(self.env, "ok", "done", extra={"foo": "bar"})
        self.assertEqual(ack["direction"], "app->ext")
        self.assertEqual(ack["type"], "ack")
        self.assertEqual(ack["payload"]["ack_msg_id"], self.env["msg_id"])
        self.assertEqual(ack["payload"]["status"], "ok")
        self.assertEqual(ack["payload"]["message"], "done")
        self.assertEqual(ack["payload"]["foo"], "bar")
        self.assertEqual(ack["session_id"], self.env["session_id"])

    def test_error_structure(self) -> None:
        err = self.host._error(self.env, "invalid_envelope", "bad msg")
        self.assertEqual(err["direction"], "app->ext")
        self.assertEqual(err["type"], "error")
        self.assertEqual(err["payload"]["code"], "invalid_envelope")
        self.assertEqual(err["payload"]["message"], "bad msg")


class NativeHostRoutingTestCase(unittest.TestCase):
    """Tests for message routing via router callback."""

    def setUp(self) -> None:
        self.calls = []

        def router(envelope):
            self.calls.append(envelope)
            return {"status": "ok"}

        self.host = NativeHost(router=router)

    def test_route_ext_to_app(self) -> None:
        env = valid_envelope(msg_type="pnr_received", payload={"pnr": "ABCD1234"})
        response = self.host.route(env)
        self.assertEqual(response["type"], "ack")
        self.assertEqual(response["payload"]["status"], "ok")
        self.assertEqual(len(self.calls), 1)

    def test_route_app_to_ext_rejected(self) -> None:
        env = valid_envelope(direction="app->ext", msg_type="open_booking")
        with self.assertRaises(InvalidEnvelopeError):
            self.host.route(env)

    def test_route_no_router_returns_ack(self) -> None:
        host = NativeHost()
        env = valid_envelope(msg_type="ack")
        response = host.route(env)
        self.assertEqual(response["type"], "ack")
        self.assertEqual(response["payload"]["status"], "ok")

    def test_route_bridge_disabled(self) -> None:
        self.host.set_enabled(False)
        env = valid_envelope(msg_type="pnr_received")
        with self.assertRaises(BridgeDisabledError):
            self.host.route(env)


def _frame_message(envelope: dict) -> bytes:
    body = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    return struct.pack("<I", len(body)) + body


class _BufferWrapper:
    """Wrap a BytesIO as a .buffer attribute of a fake stdin/stdout."""

    def __init__(self, buffer: io.BytesIO) -> None:
        self.buffer = buffer


class NativeHostStdioTestCase(unittest.TestCase):
    """Tests for length-framed stdio read/write (simulated via monkeypatch)."""

    def setUp(self) -> None:
        self.host = NativeHost()
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO()

    def test_write_message_produces_framed_output(self) -> None:
        env = valid_envelope(msg_type="ack", session_id=None)
        fake_stdout = _BufferWrapper(self.stdout)
        with patch.object(sys, "stdout", fake_stdout):
            self.host.write_message(env)
        data = self.stdout.getvalue()
        self.assertGreaterEqual(len(data), 4)
        (length,) = struct.unpack("<I", data[:4])
        self.assertEqual(length, len(data) - 4)
        decoded = json.loads(data[4:].decode("utf-8"))
        self.assertEqual(decoded["type"], "ack")

    def test_read_message_from_stdin(self) -> None:
        env = valid_envelope(msg_type="pnr_received", payload={"pnr": "ABCD1234"})
        self.stdin.write(_frame_message(env))
        self.stdin.seek(0)
        fake_stdin = _BufferWrapper(self.stdin)
        with patch.object(sys, "stdin", fake_stdin):
            result = self.host.read_message()
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "pnr_received")
        self.assertEqual(result["payload"]["pnr"], "ABCD1234")

    def test_read_message_eof_returns_none(self) -> None:
        self.stdin.seek(0)
        self.stdin.truncate(0)
        fake_stdin = _BufferWrapper(self.stdin)
        with patch.object(sys, "stdin", fake_stdin):
            result = self.host.read_message()
        self.assertIsNone(result)

    def test_invalid_json_raises(self) -> None:
        self.stdin.write(struct.pack("<I", 4) + b"bad!")
        self.stdin.seek(0)
        fake_stdin = _BufferWrapper(self.stdin)
        with patch.object(sys, "stdin", fake_stdin):
            with self.assertRaises(NativeHostError):
                self.host.read_message()


if __name__ == "__main__":
    unittest.main()
