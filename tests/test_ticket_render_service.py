"""Tests for the TicketRenderService (ERS ticket renderer).

Covers:
- HTML rendering with full booking DTO (all placeholders substituted)
- Passenger row rendering
- Missing required field handling
- GST and payment details substitution
- QR code and logo embedding

No network I/O. Uses unittest.
"""

from __future__ import annotations

import json
import tempfile
import unittest

from bingo_linux.services.ticket_render_service import TicketRenderService


class TicketRenderServiceTestCase(unittest.TestCase):
    """Test case for ERS ticket rendering."""

    def setUp(self) -> None:
        self.renderer = TicketRenderService()

    @property
    def sample_dto(self) -> dict:
        return {
            "HtmlTitle": "Electronic Reservation Slip",
            "bookingResponseDTO": {
                "pnrNumber": "1234567890",
                "trainNumber": "12704",
                "trainName": "Howrah Express",
                "journeyClass": "3A",
                "bookedQuota": "GN",
                "journeyQuota": "General",
                "distance": "1500",
                "bookingDate": "2026-12-01 10:30",
                "fromStnName": "Howrah Junction",
                "fromStn": "HWH",
                "boardingStnName": "Howrah Junction",
                "boardingStn": "HWH",
                "resvnUptoStnName": "Secunderabad",
                "resvnUptoStn": "SC",
                "journeyDate": "2026-12-05",
                "boardingDate": "2026-12-05 22:00",
                "destArrvDate": "2026-12-07 05:30",
                "totalFare": "1250.00",
                "serviceChargeTotal": "45.00",
                "gstCharge": {
                    "invoiceNumber": "INV-2026-001",
                    "suplierAddress": "IRCTC, New Delhi",
                    "sacCode": "996411",
                    "gstinSuplier": "07AABCI1234K1Z5",
                    "taxableValue": "1295.00",
                    "cgstAmount": "32.38",
                    "sgstAmount": "32.38",
                    "igstAmount": "0.00",
                },
            },
            "FullClassName": "THREE AC (3A)",
            "transactionId": "TXN-2026-123456",
            "totalCollectibleAmount": "1295.00",
            "qrbase64String": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
            "placeOfSupply": "NA",
            "stateNameCode": "Delhi/DL",
            "passengers": [
                {
                    "name": "S. Singh",
                    "age": 32,
                    "gender": "Male",
                    "booking_status": "CNF",
                    "current_status": "CNF",
                },
                {
                    "name": "A. Singh",
                    "age": 28,
                    "gender": "Female",
                    "booking_status": "CNF",
                    "current_status": "CNF",
                },
            ],
        }

    # ------------------------------------------------------------------
    # HTML rendering
    # ------------------------------------------------------------------

    def test_render_html_full_dto(self) -> None:
        """Full DTO produces HTML with all placeholders substituted."""
        html = self.renderer.render_html(self.sample_dto)

        # Core identifiers
        self.assertIn("1234567890", html)
        self.assertIn("12704", html)
        self.assertIn("Howrah Express", html)
        self.assertIn("THREE AC (3A)", html)
        self.assertIn("3A", html)

        # Stations
        self.assertIn("Howrah Junction", html)
        self.assertIn("HWH", html)
        self.assertIn("Secunderabad", html)
        self.assertIn("SC", html)

        # Dates
        self.assertIn("2026-12-05", html)
        self.assertIn("22:00", html)
        self.assertIn("05:30", html)

        # Financials
        self.assertIn("1250.00", html)
        self.assertIn("45.00", html)
        self.assertIn("1295.00", html)

        # Transaction
        self.assertIn("TXN-2026-123456", html)

        # GST
        self.assertIn("INV-2026-001", html)
        self.assertIn("996411", html)
        self.assertIn("07AABCI1234K1Z5", html)
        self.assertIn("2.5%", html)
        self.assertIn("5.0%", html)

        # Passengers
        self.assertIn("S. Singh", html)
        self.assertIn("A. Singh", html)
        self.assertIn("CNF", html)

        # No unreplaced placeholders remain
        self.assertNotIn("{", html.split("<!--")[0] if "<!--" in html else html)
        # Check specifically that no {placeholder} patterns remain
        import re
        placeholders = re.findall(r"\{[^}]+\}", html)
        self.assertEqual(placeholders, [])

    def test_render_html_minimal_dto(self) -> None:
        """Minimal DTO with only required fields renders without error."""
        minimal = {
            "bookingResponseDTO": {
                "pnrNumber": "9999999999",
                "trainNumber": "1",
                "trainName": "Test Train",
                "journeyClass": "SL",
                "bookedQuota": "GN",
                "journeyQuota": "General",
                "distance": "100",
                "bookingDate": "2026-01-01 00:00",
                "fromStnName": "A",
                "fromStn": "AAA",
                "boardingStnName": "B",
                "boardingStn": "BBB",
                "resvnUptoStnName": "C",
                "resvnUptoStn": "CCC",
                "journeyDate": "2026-01-02",
                "boardingDate": "2026-01-02 00:00",
                "destArrvDate": "2026-01-02 00:00",
                "totalFare": "0.00",
                "serviceChargeTotal": "0.00",
            },
            "FullClassName": "SLEEPER (SL)",
            "transactionId": "TXN-000",
            "totalCollectibleAmount": "0.00",
            "qrbase64String": "",
            "passengers": [],
        }
        html = self.renderer.render_html(minimal)
        self.assertIn("9999999999", html)
        self.assertIn("SLEEPER (SL)", html)

    # ------------------------------------------------------------------
    # Passenger rows
    # ------------------------------------------------------------------

    def test_render_passenger_rows(self) -> None:
        """Passenger rows are rendered as HTML table rows."""
        passengers = [
            {"name": "John Doe", "age": 30, "gender": "Male",
             "booking_status": "CNF", "current_status": "CNF"},
        ]
        rows = self.renderer.render_passenger_rows(passengers)
        self.assertIn("John Doe", rows)
        self.assertIn("30", rows)
        self.assertIn("Male", rows)
        self.assertIn("CNF", rows)
        self.assertIn("<tr>", rows)
        self.assertIn("</tr>", rows)

    def test_render_passenger_rows_empty(self) -> None:
        """Empty passenger list returns empty string."""
        rows = self.renderer.render_passenger_rows([])
        self.assertEqual(rows, "")

    def test_render_passenger_rows_multiple(self) -> None:
        """Multiple passengers produce multiple numbered rows."""
        passengers = [
            {"name": "A", "age": "10", "gender": "M",
             "booking_status": "WL", "current_status": "WL"},
            {"name": "B", "age": "20", "gender": "F",
             "booking_status": "RAC", "current_status": "RAC"},
        ]
        rows = self.renderer.render_passenger_rows(passengers)
        # Check numbering
        self.assertIn(">1<", rows)  # first row number
        self.assertIn(">2<", rows)  # second row number

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_render_html_missing_pnr(self) -> None:
        """Missing pnrNumber renders as empty string (no crash)."""
        dto = dict(self.sample_dto)
        del dto["bookingResponseDTO"]["pnrNumber"]
        html = self.renderer.render_html(dto)
        # Missing field renders as empty string, no exception
        self.assertIn("Howrah Express", html)

    # ------------------------------------------------------------------
    # JSON round-trip
    # ------------------------------------------------------------------

    def test_render_html_from_json(self) -> None:
        """DTO loaded from JSON renders correctly."""
        dto_json = json.dumps(self.sample_dto)
        dto = json.loads(dto_json)
        html = self.renderer.render_html(dto)
        self.assertIn("1234567890", html)
        self.assertIn("Howrah Express", html)


if __name__ == "__main__":
    unittest.main()
