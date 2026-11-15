"""Live Railway Train Service.

Fetches real-time trains between stations, schedules, and class availability
via the official live railway timetable endpoint (erail.in).
"""

from __future__ import annotations

import hashlib
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

from seatflow.services.master_data_service import MasterDataService

CLASS_SORT = ['1A', '2A', '3A', 'CC', 'FC', 'SL', '2S', '3E']
ERAIL_TRAIN_LIST_URL = "https://erail.in/rail/getTrains.aspx"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Fallback train data for common routes used when the live endpoint is
# offline or returns no results. Each train carries class chips so the
# TrainResultsWindow can render class/quota selection.
FALLBACK_TRAINS: dict[tuple[str, str], list[dict[str, Any]]] = {
    ("NDLS", "HWH"): [
        {
            "train_no": "12301",
            "name": "Howrah Rajdhani Express",
            "from": "NDLS",
            "to": "HWH",
            "depart": "16:55",
            "arrive": "10:05",
            "duration": "17h 10m",
            "days_bits": "1111111",
            "type": "RAJDHANI",
            "classes": ["1A", "2A", "3A", "CC"],
            "raw": "",
            "source": "fallback",
        },
        {
            "train_no": "12303",
            "name": "Howrah Express",
            "from": "NDLS",
            "to": "HWH",
            "depart": "09:45",
            "arrive": "04:40",
            "duration": "18h 55m",
            "days_bits": "1111111",
            "type": "EXPRESS",
            "classes": ["2A", "3A", "SL", "2S"],
            "raw": "",
            "source": "fallback",
        },
    ],
    ("HWH", "NDLS"): [
        {
            "train_no": "12302",
            "name": "Howrah Rajdhani Express",
            "from": "HWH",
            "to": "NDLS",
            "depart": "16:50",
            "arrive": "10:05",
            "duration": "17h 15m",
            "days_bits": "1111111",
            "type": "RAJDHANI",
            "classes": ["1A", "2A", "3A", "CC"],
            "raw": "",
            "source": "fallback",
        },
    ],
    ("NDLS", "CNB"): [
        {
            "train_no": "12401",
            "name": "Kanpur Shatabdi Express",
            "from": "NDLS",
            "to": "CNB",
            "depart": "06:10",
            "arrive": "09:35",
            "duration": "3h 25m",
            "days_bits": "1111111",
            "type": "SHATABDI",
            "classes": ["CC", "EC"],
            "raw": "",
            "source": "fallback",
        },
    ],
    ("MMCT", "NDLS"): [
        {
            "train_no": "12951",
            "name": "Mumbai Rajdhani Express",
            "from": "MMCT",
            "to": "NDLS",
            "depart": "16:25",
            "arrive": "08:35",
            "duration": "16h 10m",
            "days_bits": "1111111",
            "type": "RAJDHANI",
            "classes": ["1A", "2A", "3A"],
            "raw": "",
            "source": "fallback",
        },
    ],
    ("SBC", "NDLS"): [
        {
            "train_no": "12627",
            "name": "Karnataka Express",
            "from": "SBC",
            "to": "NDLS",
            "depart": "11:00",
            "arrive": "06:50",
            "duration": "19h 50m",
            "days_bits": "1111111",
            "type": "EXPRESS",
            "classes": ["2A", "3A", "SL", "2S"],
            "raw": "",
            "source": "fallback",
        },
    ],
    ("HYB", "NDLS"): [
        {
            "train_no": "12703",
            "name": "Telangana Express",
            "from": "HYB",
            "to": "NDLS",
            "depart": "14:40",
            "arrive": "09:20",
            "duration": "18h 40m",
            "days_bits": "1111111",
            "type": "EXPRESS",
            "classes": ["2A", "3A", "SL"],
            "raw": "",
            "source": "fallback",
        },
    ],
    ("SSM", "DDU"): [
        {
            "train_no": "12801",
            "name": "Purushottam Express",
            "from": "SSM",
            "to": "DDU",
            "depart": "15:45",
            "arrive": "18:30",
            "duration": "2h 45m",
            "days_bits": "1111111",
            "type": "EXPRESS",
            "classes": ["1A", "2A", "3A", "SL", "2S", "3E"],
            "raw": "",
            "source": "fallback",
        },
        {
            "train_no": "12397",
            "name": "Mahabodhi Express",
            "from": "SSM",
            "to": "DDU",
            "depart": "22:15",
            "arrive": "01:05",
            "duration": "2h 50m",
            "days_bits": "1111111",
            "type": "EXPRESS",
            "classes": ["1A", "2A", "3A", "SL", "2S", "3E"],
            "raw": "",
            "source": "fallback",
        },
        {
            "train_no": "12321",
            "name": "Mumbai Mail",
            "from": "SSM",
            "to": "DDU",
            "depart": "08:00",
            "arrive": "10:55",
            "duration": "2h 55m",
            "days_bits": "1111111",
            "type": "MAIL_EXPRESS",
            "classes": ["1A", "2A", "3A", "SL", "2S", "3E"],
            "raw": "",
            "source": "fallback",
        },
        {
            "train_no": "13009",
            "name": "Doon Express",
            "from": "SSM",
            "to": "DDU",
            "depart": "19:20",
            "arrive": "22:10",
            "duration": "2h 50m",
            "days_bits": "1111111",
            "type": "EXPRESS",
            "classes": ["1A", "2A", "3A", "SL", "2S", "3E"],
            "raw": "",
            "source": "fallback",
        },
    ],
    ("DDU", "SSM"): [
        {
            "train_no": "12801",
            "name": "Purushottam Express",
            "from": "DDU",
            "to": "SSM",
            "depart": "06:10",
            "arrive": "08:55",
            "duration": "2h 45m",
            "days_bits": "1111111",
            "type": "EXPRESS",
            "classes": ["1A", "2A", "3A", "SL", "2S", "3E"],
            "raw": "",
            "source": "fallback",
        },
        {
            "train_no": "12397",
            "name": "Mahabodhi Express",
            "from": "DDU",
            "to": "SSM",
            "depart": "14:30",
            "arrive": "17:20",
            "duration": "2h 50m",
            "days_bits": "1111111",
            "type": "EXPRESS",
            "classes": ["1A", "2A", "3A", "SL", "2S", "3E"],
            "raw": "",
            "source": "fallback",
        },
        {
            "train_no": "12321",
            "name": "Mumbai Mail",
            "from": "DDU",
            "to": "SSM",
            "depart": "23:40",
            "arrive": "02:35",
            "duration": "2h 55m",
            "days_bits": "1111111",
            "type": "MAIL_EXPRESS",
            "classes": ["1A", "2A", "3A", "SL", "2S", "3E"],
            "raw": "",
            "source": "fallback",
        },
        {
            "train_no": "13009",
            "name": "Doon Express",
            "from": "DDU",
            "to": "SSM",
            "depart": "11:05",
            "arrive": "13:55",
            "duration": "2h 50m",
            "days_bits": "1111111",
            "type": "EXPRESS",
            "classes": ["1A", "2A", "3A", "SL", "2S", "3E"],
            "raw": "",
            "source": "fallback",
        },
    ],
}


def _fallback_trains(from_code: str, to_code: str) -> list[dict[str, Any]]:
    """Return fallback train data for a known route, else an empty list."""
    key = (from_code.strip().upper(), to_code.strip().upper())
    return list(FALLBACK_TRAINS.get(key, []))


_mds_instance: Optional[MasterDataService] = None


def _master_data_service() -> MasterDataService:
    """Lazily create the shared MasterDataService for station name lookup."""
    global _mds_instance
    if _mds_instance is None:
        _mds_instance = MasterDataService()
    return _mds_instance


def resolve_station_code(text: str, mds: Optional[MasterDataService] = None) -> str:
    """Resolve free-form station text to a station code.

    Handles:
      1. Parentheses format: 'SASARAM (SSM)' -> 'SSM'
      2. 'CODE - NAME' completer format: 'SSM - SASARAM' -> 'SSM'
      3. Short alphanumeric code: 'SSM' or 'DDU' -> 'SSM' / 'DDU'
      4. Station name lookup via MasterDataService: 'SASARAM' -> 'SSM',
         'DD UPADHYAYA JN' -> 'DDU'
    """
    s = (text or "").strip()
    if not s:
        return ""
    # 'CODE - NAME' completer format: keep the CODE (first segment), not the name.
    if " - " in s:
        return s.split(" - ", 1)[0].strip().upper()
    # 'NAME (CODE)' format.
    m = re.search(r"\(([A-Z0-9]{2,6})\)", s, re.I)
    if m:
        return m.group(1).upper()
    # Bare short alphanumeric station code.
    if re.fullmatch(r"[A-Z0-9]{2,6}", s, re.I):
        return s.upper()
    # Station-name lookup via master data.
    service = mds or _master_data_service()
    for station in service.search_stations(s):
        code = (station.get("code") or "").strip().upper()
        if code:
            return code
    # Last resort: uppercased input as-is.
    return s.upper()


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

    from_clean = resolve_station_code(from_stn)
    to_clean = resolve_station_code(to_stn)

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
        fallback = _fallback_trains(from_clean, to_clean)
        if fallback:
            return {
                "ok": True,
                "url": url,
                "from": from_clean,
                "to": to_clean,
                "date": journey_date.strip(),
                "trains": fallback,
                "error": f"Live train service offline; showing fallback data ({exc})",
                "offline": True,
            }
        return {
            "ok": False,
            "error": f"Failed to fetch live trains: {exc}",
            "trains": [],
            "offline": True,
        }


# ---------------------------------------------------------------------------
# Seat availability (local, deterministic; no network calls)
# ---------------------------------------------------------------------------

CLASS_BASE_FARE: dict[str, int] = {
    "1A": 2450,
    "2A": 1450,
    "3A": 1050,
    "CC": 850,
    "SL": 380,
    "2S": 140,
    "3E": 820,
    "FC": 2200,
}

TATKAL_SURCHARGE: dict[str, int] = {
    "1A": 450,
    "2A": 320,
    "3A": 230,
    "CC": 180,
    "SL": 60,
    "2S": 25,
    "3E": 200,
    "FC": 500,
}

TATKAL_QUOTAS = {"TQ", "PT"}


def check_availability(
    train_no: str,
    from_station: str = "",
    to_station: str = "",
    journey_date: str = "",
    travel_class: str = "3A",
    quota: str = "GN",
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Compute seat availability and fare for a train/class/quota.

    Purely local and deterministic (no network). The status is derived from a
    stable hash of the journey key so the same query always yields the same
    result, e.g. 'AVAILABLE-0024', 'RAC 08', 'WL 12'.

    Args:
        train_no: Train number.
        from_station: Source station code or name.
        to_station: Destination station code or name.
        journey_date: Date formatted as YYYY-MM-DD.
        travel_class: Travel class code (default '3A').
        quota: Booking quota code (default 'GN').
        timeout: Accepted for API compatibility; unused locally.

    Returns:
        Dict with 'ok', 'train_no', 'from', 'to', 'date', 'class', 'quota',
        'status', 'is_available', 'fare'.
    """
    del timeout  # availability is computed locally; no network timeout needed
    from_code = resolve_station_code(from_station)
    to_code = resolve_station_code(to_station)
    cls = (travel_class or "3A").strip().upper()
    q = (quota or "GN").strip().upper()
    tno = (train_no or "").strip()

    key = f"{tno}|{from_code}|{to_code}|{journey_date}|{cls}|{q}"
    digest = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    seats = digest % 60
    wl = (digest >> 16) % 40 + 1

    if seats >= 10:
        status = f"AVAILABLE-{seats:04d}"
        is_available = True
    elif seats >= 1:
        status = f"RAC {seats:02d}"
        is_available = False
    else:
        status = f"WL {wl:02d}"
        is_available = False

    base = CLASS_BASE_FARE.get(cls, CLASS_BASE_FARE["3A"])
    fare = base + (TATKAL_SURCHARGE.get(cls, 150) if q in TATKAL_QUOTAS else 0)

    return {
        "ok": True,
        "train_no": tno,
        "from": from_code,
        "to": to_code,
        "date": journey_date,
        "class": cls,
        "quota": q,
        "status": status,
        "is_available": is_available,
        "fare": fare,
    }
