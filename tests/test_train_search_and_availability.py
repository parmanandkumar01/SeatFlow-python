"""Station code resolution, train search parity, and seat availability.

Covers:
1. resolve_station_code for 'CODE - NAME', 'NAME (CODE)', bare codes, and
   station-name lookups via MasterDataService.
2. fetch_train_list parity for Grand Chord route SSM <-> DDU (fallback
   trains with class chips).
3. check_availability shape: ok=True, status string, fare, quota.
4. BookWindow / TrainResultsWindow availability integration, including the
   Application signal wiring for availability_clicked.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from PySide6.QtWidgets import QApplication

from seatflow.app.application import Application
from seatflow.database.database import Database
from seatflow.services.train_service import (
    check_availability,
    fetch_train_list,
    resolve_station_code,
)
from seatflow.ui.book_window import BookWindow
from seatflow.ui.train_results_window import ClassChip, TrainResultsWindow

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class _BaseTestCase(unittest.TestCase):
    """Base case with a temporary database and an Application controller."""

    def setUp(self) -> None:
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        self.db = Database(db_path=self.tmp_path)
        self.db.initialize_schema()
        self.controller = Application()
        self.controller._db = self.db

    def tearDown(self) -> None:
        try:
            self.controller.shutdown()
        except Exception:
            pass
        self.db.close()
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)


# ---------------------------------------------------------------------------
# Step 1: Station code resolution
# ---------------------------------------------------------------------------

class TestStationCodeResolution(unittest.TestCase):
    def test_code_name_format_keeps_code(self):
        self.assertEqual(resolve_station_code("SSM - SASARAM"), "SSM")
        self.assertEqual(resolve_station_code("DDU - DD UPADHYAYA JN"), "DDU")

    def test_parentheses_format(self):
        self.assertEqual(resolve_station_code("SASARAM (SSM)"), "SSM")

    def test_bare_code(self):
        self.assertEqual(resolve_station_code("SSM"), "SSM")
        self.assertEqual(resolve_station_code("DDU"), "DDU")

    def test_station_name_lookup(self):
        self.assertEqual(resolve_station_code("SASARAM"), "SSM")
        self.assertEqual(resolve_station_code("DD UPADHYAYA JN"), "DDU")

    def test_empty_input(self):
        self.assertEqual(resolve_station_code(""), "")
        self.assertEqual(resolve_station_code("   "), "")


# ---------------------------------------------------------------------------
# Step 1: Train search parity (Grand Chord fallback routes)
# ---------------------------------------------------------------------------

class TestTrainSearchParity(unittest.TestCase):
    def _offline(self, from_code: str, to_code: str) -> dict:
        with mock.patch(
            "seatflow.services.train_service.httpx.Client",
            side_effect=Exception("network offline"),
        ):
            return fetch_train_list(from_code, to_code, "2026-12-01")

    def test_fetch_train_list_ssm_ddu_returns_trains_with_classes(self):
        res = self._offline("SSM", "DDU")
        self.assertTrue(res.get("ok"))
        trains = res.get("trains", [])
        self.assertGreaterEqual(len(trains), 1, "fallback trains should be returned offline")
        for t in trains:
            self.assertEqual(t["from"], "SSM")
            self.assertEqual(t["to"], "DDU")
            self.assertEqual(
                t["classes"], ["1A", "2A", "3A", "SL", "2S", "3E"]
            )
            self.assertTrue(t["train_no"])

    def test_fetch_train_list_ddu_ssm_returns_trains_with_classes(self):
        res = self._offline("DDU", "SSM")
        self.assertTrue(res.get("ok"))
        trains = res.get("trains", [])
        self.assertGreaterEqual(len(trains), 1)
        for t in trains:
            self.assertEqual(t["from"], "DDU")
            self.assertEqual(t["to"], "SSM")
            self.assertEqual(
                t["classes"], ["1A", "2A", "3A", "SL", "2S", "3E"]
            )

    def test_fallback_contains_authentic_grand_chord_trains(self):
        res = self._offline("SSM", "DDU")
        numbers = {t["train_no"] for t in res["trains"]}
        for expected in ("12801", "12397", "12321", "13009"):
            self.assertIn(expected, numbers)
        names = {t["train_no"]: t["name"] for t in res["trains"]}
        self.assertEqual(names["12801"], "Purushottam Express")
        self.assertEqual(names["12397"], "Mahabodhi Express")
        self.assertEqual(names["12321"], "Mumbai Mail")
        self.assertEqual(names["13009"], "Doon Express")


# ---------------------------------------------------------------------------
# Step 2: Seat availability service
# ---------------------------------------------------------------------------

class TestCheckAvailability(unittest.TestCase):
    def test_check_availability_shape(self):
        res = check_availability(
            "12801", "SSM", "DDU", "2026-12-01", travel_class="3A", quota="GN"
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["train_no"], "12801")
        self.assertEqual(res["from"], "SSM")
        self.assertEqual(res["to"], "DDU")
        self.assertEqual(res["date"], "2026-12-01")
        self.assertEqual(res["class"], "3A")
        self.assertEqual(res["quota"], "GN")
        self.assertIsInstance(res["status"], str)
        self.assertTrue(
            res["status"].startswith(("AVAILABLE-", "RAC ", "WL "))
        )
        self.assertIsInstance(res["is_available"], bool)
        self.assertEqual(
            res["is_available"], res["status"].startswith("AVAILABLE-")
        )
        self.assertIsInstance(res["fare"], int)
        self.assertGreater(res["fare"], 0)

    def test_deterministic_same_query_same_result(self):
        r1 = check_availability("12801", "SSM", "DDU", "2026-12-01", "3A", "GN")
        r2 = check_availability("12801", "SSM", "DDU", "2026-12-01", "3A", "GN")
        self.assertEqual(r1, r2)

    def test_station_names_resolved_to_codes(self):
        res = check_availability(
            "12801", "SASARAM", "DD UPADHYAYA JN", "2026-12-01", "3A", "GN"
        )
        self.assertEqual(res["from"], "SSM")
        self.assertEqual(res["to"], "DDU")

    def test_fare_by_class_and_quota(self):
        base_3a = check_availability("12801", "SSM", "DDU", "2026-12-01", "3A", "GN")["fare"]
        self.assertEqual(base_3a, 1050)
        self.assertEqual(
            check_availability("12801", "SSM", "DDU", "2026-12-01", "SL", "GN")["fare"],
            380,
        )
        self.assertEqual(
            check_availability("12801", "SSM", "DDU", "2026-12-01", "2S", "GN")["fare"],
            140,
        )
        # Tatkal / Premium Tatkal attract a surcharge.
        self.assertEqual(
            check_availability("12801", "SSM", "DDU", "2026-12-01", "3A", "TQ")["fare"],
            1050 + 230,
        )
        self.assertEqual(
            check_availability("12801", "SSM", "DDU", "2026-12-01", "3A", "PT")["fare"],
            1050 + 230,
        )

    def test_status_variants(self):
        statuses = {
            check_availability(n, "SSM", "DDU", "2026-12-01", "3A", "GN")["status"]
            for n in ("12801", "12397", "12321", "13009")
        }
        self.assertTrue(
            any(s.startswith("AVAILABLE-") for s in statuses)
            or any(s.startswith("RAC ") for s in statuses)
            or any(s.startswith("WL ") for s in statuses)
        )


# ---------------------------------------------------------------------------
# Steps 3-4: UI + signal wiring integration
# ---------------------------------------------------------------------------

class TestBookWindowAvailability(unittest.TestCase):
    def test_set_availability_status_shows_pill(self):
        win = BookWindow()
        try:
            win.set_availability_status("AVAILABLE-0024", is_available=True, fare=1050)
            self.assertEqual(win.avail_pill.text(), "AVAILABLE-0024 | ₹1,050")
            self.assertIn("bbf7d0", win.avail_pill.styleSheet())

            win.set_availability_status("WL 12", is_available=False, fare=380)
            self.assertEqual(win.avail_pill.text(), "WL 12 | ₹380")
            self.assertIn("fdba74", win.avail_pill.styleSheet())

            # Text-only call keeps the text unchanged when fare is None.
            win.set_availability_status("RAC 08", is_available=False)
            self.assertEqual(win.avail_pill.text(), "RAC 08")
        finally:
            win.hide()
            win.deleteLater()

    def test_apply_train_selection_applies_availability(self):
        win = BookWindow()
        try:
            win.apply_train_selection({
                "trainNo": "12801",
                "trainName": "Purushottam Express",
                "trainClass": "3A",
                "quota": "GN",
                "from": "SSM",
                "to": "DDU",
                "availability": "AVAILABLE-0024",
                "fare": 1050,
                "is_available": True,
            })
            self.assertEqual(win.train_edit.text(), "Purushottam Express (12801)")
            self.assertEqual(win.avail_pill.text(), "AVAILABLE-0024 | ₹1,050")
            idx = win.class_combo.findData("3A")
            self.assertEqual(win.class_combo.itemData(idx), "3A")
        finally:
            win.hide()
            win.deleteLater()


class TestTrainResultsWindowAvailability(unittest.TestCase):
    def test_chip_clicked_emits_availability_and_fare(self):
        with mock.patch(
            "seatflow.services.train_service.httpx.Client",
            side_effect=Exception("network offline"),
        ):
            res = fetch_train_list("SSM", "DDU", "2026-12-01")

        win = TrainResultsWindow()
        try:
            win.set_trains(
                res["trains"],
                {"from": "SSM", "to": "DDU", "date": "2026-12-01"},
            )
            emitted = []
            win.apply_selection.connect(lambda d: emitted.append(d))

            chips_widget = win.table.cellWidget(0, 8)
            chip = chips_widget.findChild(ClassChip)
            self.assertIsNotNone(chip)
            chip.click()

            self.assertEqual(len(emitted), 1)
            sel = emitted[0]
            self.assertIn("availability", sel)
            self.assertIn("fare", sel)
            self.assertIn("is_available", sel)
            self.assertIsInstance(sel["fare"], int)
            self.assertGreater(sel["fare"], 0)
            self.assertTrue(
                sel["availability"].startswith(("AVAILABLE-", "RAC ", "WL "))
            )
            self.assertEqual(sel["is_available"], sel["availability"].startswith("AVAILABLE-"))
            self.assertIn("₹", win.banner_text.text())
        finally:
            win.hide()
            win.deleteLater()


class TestApplicationAvailabilityWiring(_BaseTestCase):
    def test_availability_clicked_wired_to_check_handler(self):
        self.controller.create_main_window()
        self.assertIsNotNone(self.controller._book_window)
        self.assertIsNotNone(self.controller._train_results_window)

    def test_on_check_availability_with_train_and_class_updates_pill(self):
        self.controller.create_main_window()
        bw = self.controller._book_window
        bw.from_edit.setText("SSM")
        bw.to_edit.setText("DDU")
        bw.train_edit.setText("12801")
        idx = bw.class_combo.findData("3A")
        bw.class_combo.setCurrentIndex(idx)

        date_str = bw.date_edit.date().toString("yyyy-MM-dd")
        quota = bw.quota_combo.currentData()
        expected = check_availability(
            "12801", "SSM", "DDU", date_str, travel_class="3A", quota=quota
        )
        dot = "🟢" if expected["is_available"] else "🟡"
        expected_text = f"{dot} {expected['status']} | ₹{expected['fare']:,} | {quota}"

        bw.availability_clicked.emit()
        self.assertEqual(bw.avail_pill.text(), expected_text)

    def test_on_check_availability_without_train_opens_results_window(self):
        self.controller.create_main_window()
        bw = self.controller._book_window
        trw = self.controller._train_results_window
        bw.from_edit.setText("SSM")
        bw.to_edit.setText("DDU")
        bw.train_edit.clear()
        bw.class_combo.setCurrentIndex(0)  # '- Select -'

        trw.hide()
        bw.availability_clicked.emit()

        self.assertTrue(trw.isVisible())
        self.assertIn(
            "CHECKING AVAILABILITY FOR SSM → DDU", trw.banner_text.text()
        )
        trw.hide()


if __name__ == "__main__":
    unittest.main()
