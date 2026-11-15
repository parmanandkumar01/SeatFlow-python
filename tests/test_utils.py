"""Tests for the shared ``bingo_linux.utils`` helpers.

Every expectation here was cross-checked against the original renderer bundle
``assets/utils-pOwDnddK.js`` by loading the deobfuscated module in Node and
comparing outputs across a broad input matrix (107 scalar/container cases, 27
watermark cases and 378 tatkal cases).  The tests therefore pin observable
behaviour, not implementation details.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from bingo_linux.utils import (
    DEFAULT_FONT_SIZE,
    DEFAULT_HEIGHT,
    DEFAULT_LETTER_SPACING,
    DEFAULT_TEXT,
    DEFAULT_WIDTH,
    QUOTA_LABELS,
    TRAIN_CLASS_LABELS,
    display_to_iso,
    extract_train_number,
    gateway_slug,
    iso_to_display,
    js_number,
    js_string,
    js_truthy,
    quota_label,
    svg_watermark,
    tatkal_adjust,
    today_utc,
    tomorrow_utc,
    train_class_label,
)


class JsCoercionTestCase(unittest.TestCase):
    """The renderer relies on implicit ``String()`` coercion."""

    def test_js_string_scalars(self) -> None:
        cases = [
            (None, ""),
            ("", ""),
            ("abc", "abc"),
            (True, "true"),
            (False, "false"),
            (0, "0"),
            (123, "123"),
            (13.5, "13.5"),
            (130.0, "130"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(js_string(value), expected)

    def test_js_string_containers(self) -> None:
        self.assertEqual(js_string([]), "")
        self.assertEqual(js_string([1, 2]), "1,2")
        self.assertEqual(js_string([1, [2, 3]]), "1,2,3")
        self.assertEqual(js_string([None]), "")
        self.assertEqual(js_string({}), "[object Object]")

    def test_js_number(self) -> None:
        self.assertEqual(js_number(130), "130")
        self.assertEqual(js_number(130.0), "130")
        self.assertEqual(js_number(50.5), "50.5")
        self.assertEqual(js_number(0.4), "0.4")

    def test_js_truthy(self) -> None:
        for value in (None, False, 0, 0.0, "", float("nan")):
            with self.subTest(value=value):
                self.assertFalse(js_truthy(value))
        for value in (True, 1, -1, "0", "false", [], {}, [0]):
            with self.subTest(value=value):
                self.assertTrue(js_truthy(value))


class GatewaySlugTestCase(unittest.TestCase):
    """``gateway_slug`` mirrors the renderer's label-to-slug helper."""

    def test_basic_labels(self) -> None:
        cases = [
            ("IRCTC  New Delhi - Mumbai Rajdhani Express",
             "NEW-DELHI---MUMBAI-RAJDHANI-EXPRESS"),
            ("IRCTC   Rajdhani  ", "RAJDHANI"),
            ("  plain  train  ", "PLAIN-TRAIN"),
            ("IRCTC\tTab\tSep", "TAB-SEP"),
            ("a-b c", "A-B-C"),
            ("A  B", "A-B"),
            ("irctc new delhi", "NEW-DELHI"),
            (" IRCTC X", "X"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(gateway_slug(value), expected)

    def test_leading_irctc_requires_trailing_whitespace(self) -> None:
        self.assertEqual(gateway_slug("IRCTC"), "IRCTC")
        self.assertEqual(gateway_slug("IRCTC  "), "IRCTC")
        self.assertEqual(gateway_slug("IRCTCX Y"), "IRCTCX-Y")
        self.assertEqual(gateway_slug("XIRCTCY train"), "XIRCTCY-TRAIN")

    def test_empty_and_falsy(self) -> None:
        for value in ("", "   ", None, False, 0):
            with self.subTest(value=value):
                self.assertEqual(gateway_slug(value), "")

    def test_truthy_non_strings(self) -> None:
        self.assertEqual(gateway_slug(123), "123")
        self.assertEqual(gateway_slug(True), "TRUE")
        self.assertEqual(gateway_slug([1, 2]), "1,2")
        self.assertEqual(gateway_slug({}), "[OBJECT-OBJECT]")


class DateConversionTestCase(unittest.TestCase):
    """``iso_to_display`` is a prefix match; ``display_to_iso`` is anchored."""

    def test_iso_to_display(self) -> None:
        cases = [
            ("2026-11-15", "15-11-2026"),
            ("2026-11-15T23:59:59.999Z", "15-11-2026"),
            ("2026-11-15x", "15-11-2026"),
            ("2026-11-15-2026-11-16", "15-11-2026"),
            ("2026-01-05", "05-01-2026"),
            ("2026-13-01", "01-13-2026"),
            ("0000-00-00", "00-00-0000"),
            # Not a leading ISO date: returned unchanged.
            ("2026-1-5", "2026-1-5"),
            ("x2026-11-15", "x2026-11-15"),
            ("15-11-2026", "15-11-2026"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(iso_to_display(value), expected)

    def test_iso_to_display_falsy_and_non_strings(self) -> None:
        for value in ("", None, False, 0):
            with self.subTest(value=value):
                self.assertEqual(iso_to_display(value), "")
        self.assertEqual(iso_to_display(123), 123)
        self.assertEqual(iso_to_display([]), [])

    def test_display_to_iso(self) -> None:
        cases = [
            ("15-11-2026", "2026-11-15"),
            ("01-05-2026", "2026-05-01"),
            ("31-12-1999", "1999-12-31"),
            # Already ISO: returned unchanged.
            ("2026-11-15", "2026-11-15"),
            # Anchored match fails.
            ("15-11-2026 ", ""),
            ("15-11-2026T00", ""),
            ("15-11-26", ""),
            ("1-5-2026", ""),
            ("15/11/2026", ""),
            ("2026-1-5", ""),
            ("2026-11-15T00:00:00Z", ""),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(display_to_iso(value), expected)

    def test_display_to_iso_falsy_and_non_strings(self) -> None:
        for value in ("", None, False, 0):
            with self.subTest(value=value):
                self.assertEqual(display_to_iso(value), "")
        self.assertEqual(display_to_iso(123), "")
        self.assertEqual(display_to_iso([]), "")


class TodayHelpersTestCase(unittest.TestCase):
    """``today_utc``/``tomorrow_utc`` follow the renderer's UTC slicing."""

    def test_format(self) -> None:
        for value in (today_utc(), tomorrow_utc()):
            with self.subTest(value=value):
                self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}$")

    def test_tomorrow_is_next_day(self) -> None:
        today = datetime.strptime(today_utc(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        tomorrow = datetime.strptime(tomorrow_utc(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        self.assertEqual(tomorrow - today, timedelta(days=1))


class ExtractTrainNumberTestCase(unittest.TestCase):
    """``extract_train_number`` finds the first standalone 4-5 digit run."""

    def test_matches(self) -> None:
        cases = [
            ("12951", "12951"),
            ("  12951  ", "12951"),
            ("12951-12952", "12951"),
            ("12951\n", "12951"),
            ("12951.5", "12951"),
            (" 12951 12952 ", "12951"),
            ("00000", "00000"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(extract_train_number(value), expected)

    def test_no_match_returns_trimmed_input(self) -> None:
        cases = [
            ("abc", "abc"),
            ("  abc  ", "abc"),
            ("12 951", "12 951"),
            ("123456", "123456"),
            ("a12951b", "a12951b"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(extract_train_number(value), expected)

    def test_falsy_and_non_strings(self) -> None:
        for value in ("", None, False, 0):
            with self.subTest(value=value):
                self.assertIsNone(extract_train_number(value))
        # Whitespace-only strings are truthy: they trim to "".
        self.assertEqual(extract_train_number("   "), "")
        self.assertEqual(extract_train_number(123), "123")
        self.assertEqual(extract_train_number(True), "true")
        self.assertEqual(extract_train_number([1, 2]), "1,2")


class MappingTestCase(unittest.TestCase):
    """Class and quota lookups return the renderer's exact labels."""

    def test_class_labels(self) -> None:
        cases = [
            ("2S", "Second Sitting (2S)"),
            ("SL", "Sleeper (SL)"),
            ("3A", "AC 3 Tier (3A)"),
            ("2A", "AC 2 Tier (2A)"),
            ("1A", "First AC (1A)"),
            ("CC", "Chair Car (CC)"),
            ("EC", "Executive Chair (EC)"),
            ("3E", "3rd AC Economy (3E)"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(train_class_label(value), expected)

    def test_class_label_unknown_and_falsy(self) -> None:
        self.assertEqual(train_class_label("XX"), "XX")
        for value in ("", None, False, 0):
            with self.subTest(value=value):
                self.assertEqual(train_class_label(value), "")

    def test_quota_labels(self) -> None:
        cases = [
            ("GN", "GENERAL"),
            ("TQ", "TATKAL"),
            ("PT", "PREMIUM TATKAL"),
            ("LD", "LADIES"),
            ("SS", "SR. CITIZEN"),
            ("DP", "DUTY PASS"),
            ("HP", "HANDICAPPED"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(quota_label(value), expected)

    def test_quota_label_unknown_and_falsy(self) -> None:
        self.assertEqual(quota_label("ZZ"), "ZZ")
        for value in ("", None, False, 0):
            with self.subTest(value=value):
                self.assertEqual(quota_label(value), "")

    def test_tables_are_complete(self) -> None:
        self.assertEqual(len(TRAIN_CLASS_LABELS), 8)
        self.assertEqual(len(QUOTA_LABELS), 7)


class TatkalAdjustTestCase(unittest.TestCase):
    """``tatkal_adjust`` corrects timestamps inside the Tatkal window."""

    @staticmethod
    def _delta(hour: int, minute: int, second: int) -> float:
        moment = datetime(2026, 11, 15, hour, minute, second)
        return (tatkal_adjust(moment) - moment).total_seconds()

    def test_outside_window_is_unchanged(self) -> None:
        for hour in (8, 9, 12, 13, 23):
            for minute in (0, 1, 2, 30, 59):
                for second in (0, 1, 30, 59):
                    with self.subTest(hour=hour, minute=minute, second=second):
                        self.assertEqual(self._delta(hour, minute, second), 0.0)

    def test_minute_zero_is_unchanged(self) -> None:
        for hour in (10, 11):
            for second in (0, 1, 30, 59):
                with self.subTest(hour=hour, second=second):
                    self.assertEqual(self._delta(hour, 0, second), 0.0)

    def test_first_minute_uses_capped_seconds(self) -> None:
        # min(second + 1, 30)
        expected = {0: -1.0, 1: -2.0, 15: -16.0, 29: -30.0, 30: -30.0, 45: -30.0, 59: -30.0}
        for hour in (10, 11):
            for second, delta in expected.items():
                with self.subTest(hour=hour, second=second):
                    self.assertEqual(self._delta(hour, 1, second), delta)

    def test_later_minutes_use_fixed_offset(self) -> None:
        for hour in (10, 11):
            for minute in (2, 5, 15, 29, 30, 45, 59):
                for second in (0, 1, 30, 59):
                    with self.subTest(hour=hour, minute=minute, second=second):
                        self.assertEqual(self._delta(hour, minute, second), -40.0)

    def test_returns_original_moment_when_unchanged(self) -> None:
        moment = datetime(2026, 11, 15, 9, 30, 0)
        self.assertIs(tatkal_adjust(moment), moment)

    def test_non_datetime_passthrough(self) -> None:
        for value in ("2026-11-15", 123, None, True):
            with self.subTest(value=value):
                self.assertIs(tatkal_adjust(value), value)


class SvgWatermarkTestCase(unittest.TestCase):
    """``svg_watermark`` reproduces the renderer's data-URI exactly."""

    def test_golden_output(self) -> None:
        expected = (
            'url("data:image/svg+xml,'
            "%3Csvg%20xmlns%3D'http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg'"
            "%20width%3D'400'%20height%3D'200'%3E"
            "%3Ctext%20x%3D'200'%20y%3D'128.0'%20fill%3D'%23000'"
            "%20font-family%3D'Inter%2CArial%2Csans-serif'"
            "%20font-size%3D'28'%20font-weight%3D'800'"
            "%20letter-spacing%3D'2'%20text-anchor%3D'middle'"
            "%20transform%3D'rotate(-30%20200%20100)'%3E"
            "BINGO%3C%2Ftext%3E%3C%2Fsvg%3E\")"
        )
        self.assertEqual(
            svg_watermark("BINGO", width=400, height=200, font_size=28, letter_spacing=2),
            expected,
        )

    def test_defaults(self) -> None:
        self.assertEqual(DEFAULT_WIDTH, 130)
        self.assertEqual(DEFAULT_HEIGHT, 62)
        self.assertEqual(DEFAULT_FONT_SIZE, 13)
        self.assertEqual(DEFAULT_LETTER_SPACING, 0.4)
        result = svg_watermark("X")
        self.assertIn("%20width%3D'130'%20height%3D'62'", result)
        self.assertIn("%20font-size%3D'13'", result)
        self.assertIn("%20letter-spacing%3D'0.4'", result)
        self.assertIn("%20y%3D'39.7'", result)  # 62 * 0.64 = 39.68 -> 39.7

    def test_fractional_dimensions(self) -> None:
        result = svg_watermark("T", width=101, height=63, font_size=13.5, letter_spacing=1.25)
        self.assertIn("%20x%3D'50.5'", result)
        self.assertIn("%20y%3D'40.3'", result)
        self.assertIn("%20font-size%3D'13.5'", result)
        self.assertIn("%20letter-spacing%3D'1.25'", result)
        self.assertIn("rotate(-30%2050.5%2031.5)", result)

    def test_falsy_text_uses_default(self) -> None:
        for value in ("", None, 0, False):
            with self.subTest(value=value):
                self.assertIn(DEFAULT_TEXT.replace(" ", "%20"), svg_watermark(value))

    def test_truthy_text_is_sanitised(self) -> None:
        # & < > become spaces; surrounding whitespace is trimmed.
        self.assertIn("%3EA%20B%20C%3C", svg_watermark("A&B<C>"))
        self.assertIn("%3EA%20%20B%3C", svg_watermark("A&&B"))
        self.assertIn("%3EA%3C", svg_watermark("  A  "))
        self.assertIn("%3Ex%20y%3C", svg_watermark("x y"))

    def test_text_is_percent_encoded_not_xml_escaped(self) -> None:
        self.assertIn("%C3%A9", svg_watermark("é"))
        self.assertIn("%E6%97%A5%E6%9C%AC", svg_watermark("日本"))
        self.assertIn("%3E100%25%3C", svg_watermark("100%"))

    def test_quotes_are_not_encoded(self) -> None:
        self.assertIn("%3Equote%22d'%3C", svg_watermark("quote\"d'"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()