"""Live Railway Train Service.

Fetches real-time trains between stations, schedules, and class availability
via the official live railway timetable endpoint (erail.in).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlencode

try:
    import httpx
    _HAVE_HTTPX = True
except ImportError:
    _HAVE_HTTPX = False

import urllib.request

CLASS_SORT = ['1A', '2A', '3A', 'CC', 'FC', 'SL', '2S', '3E']
ERAIL_TRAIN_LIST_URL = "https://erail.in/rail/getTrains.aspx"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def class_sort_key(cls: str) -> int:
    """Return sort index for travel classes."""
    try:
        return CLASS_SORT.index(cls.strip().upper())
    except (ValueError, AttributeError):
        return 999


def clean_erail_time(t: str) -> str:
    """Clean time format e.g. 18.40 to 18:40."""
    return (t or "").strip().replace(".", ":")


def find_classes_from_raw(raw: str) -> list[str]:
    """Extract list of travel classes from raw train record."""
    found = set()
    for m in re.finditer(r"(^|[|:,~])([123]A|2S|SL|CC|3E|FC)(?=[:|,|~])", raw):
        found.add(m.group(2))
    for m in re.finditer(r"(?<![A-Z])(1A|2A|3A|3E|SL|2S|CC|FC)(?=[:, \s|])", raw):
        found.add(m.group(1))
    return sorted(list(found), key=class_sort_key)


def guess_erail_train_type(chunk: str) -> str:
    """Guess train type from raw record."""
    up = re.sub(r"\s+", " ", (chunk or "").strip().upper())
    cats = [
        'SUPERFAST', 'MAIL_&_EXPRESS', 'MAIL_EXPRESS', 'HUMSAFAR',
        'ANTYODAYA', 'RAJDHANI', 'SHATABDI', 'DURONTO',
        'JAN_SHATABDI', 'SPECIAL', 'PASSENGER', 'ORDINARY'
    ]
    for c in cats:
        if c in up or c.replace("_", " ") in up:
            return c
    return "EXP"


def runs_on_date(days_bits: str, iso_date: str) -> bool:
    """Check if train runs on the given ISO date (YYYY-MM-DD)."""
    bits = (days_bits or "").strip()
    if not re.fullmatch(r"[01]{7}", bits):
        return True
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d")
        dow = d.weekday()  # 0=Monday .. 6=Sunday
        return bits[dow] == "1"
    except Exception:
        return True


def parse_erail_train_records(text: str) -> list[dict[str, Any]]:
    """Parse raw erail pipe/caret-delimited text into structured train dicts."""
    trains = []
    if not text:
        return trains
    parts = text.split("^")
    for rec in parts[1:]:
        row = rec.split("~")
        if len(row) >= 13:
            train_no = row[0].strip()
            name = row[1].strip()
            board_code = row[2].strip().upper()
            alight_code = row[3].strip().upper()
            depart = clean_erail_time(row[9])
            arrive = clean_erail_time(row[10])
            duration = row[11].strip()
            days_bits = row[12].strip()
            typ = guess_erail_train_type(rec)
            classes = find_classes_from_raw(rec)

            trains.append({
                "train_no": train_no,
                "name": name,
                "from": board_code,
                "to": alight_code,
                "depart": depart,
                "arrive": arrive,
                "duration": duration,
                "days_bits": days_bits,
                "type": typ,
                "classes": classes,
                "raw": rec,
            })
    return trains


def build_erail_train_list_url(from_code: str, to_code: str) -> str:
    """Construct URL for live train search."""
    params = {
        "Station_From": from_code.strip().upper(),
        "Station_To": to_code.strip().upper(),
        "DataSource": "0",
        "Language": "0",
        "Cache": "true",
    }
    return f"{ERAIL_TRAIN_LIST_URL}?{urlencode(params)}"


def fetch_train_list(
    from_stn: str = "",
    to_stn: str = "",
    journey_date: str = "",
    timeout: float = 15.0,
    query: Optional[dict] = None,
) -> dict[str, Any]:
    """Fetch live trains between two stations on a given journey date.

    Args:
        from_stn: Source station code (e.g., 'NDLS', 'BWN').
        to_stn: Destination station code (e.g., 'CNB', 'KAN').
        journey_date: Date formatted as YYYY-MM-DD.
        timeout: Network timeout in seconds.
        query: Optional dictionary with 'from', 'to', 'date'.

    Returns:
        Dict with 'ok' (bool), 'trains' (list of train dicts), and 'error' (if any).
    """
    if query:
        from_stn = from_stn or query.get("from", "")
        to_stn = to_stn or query.get("to", "")
        journey_date = journey_date or query.get("date", "")

    from_clean = from_stn.strip().upper()
    if " - " in from_clean:
        from_clean = from_clean.split(" - ")[-1].strip()
    m_from = re.search(r"\(([A-Z0-9]{2,6})\)", from_clean, re.I)
    if m_from:
        from_clean = m_from.group(1).upper()

    to_clean = to_stn.strip().upper()
    if " - " in to_clean:
        to_clean = to_clean.split(" - ")[-1].strip()
    m_to = re.search(r"\(([A-Z0-9]{2,6})\)", to_clean, re.I)
    if m_to:
        to_clean = m_to.group(1).upper()

    if not from_clean or not to_clean:
        return {
            "ok": False,
            "error": "Source and destination station codes are required.",
            "trains": [],
        }

    url = build_erail_train_list_url(from_clean, to_clean)
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "*/*",
        "Referer": "https://erail.in/trains-between-stations/",
        "X-Requested-With": "XMLHttpRequest",
    }

    try:
        raw_text = ""
        if _HAVE_HTTPX:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                res = client.get(url, headers=headers)
                if res.status_code >= 400:
                    return {
                        "ok": False,
                        "error": f"Live train API HTTP {res.status_code}",
                        "trains": [],
                    }
                raw_text = res.text
        else:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_text = resp.read().decode("utf-8", errors="replace")

        all_trains = parse_erail_train_records(raw_text)
        iso_date = journey_date.strip()
        trains = [t for t in all_trains if runs_on_date(t.get("days_bits", ""), iso_date)]

        return {
            "ok": True,
            "url": url,
            "from": from_clean,
            "to": to_clean,
            "date": iso_date,
            "trains": trains,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Failed to fetch live trains: {exc}",
            "trains": [],
        }
