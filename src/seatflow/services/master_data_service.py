"""Railway master data service for offline station and train lookups.

Loads and indexes official Indian Railways datasets (8,464 stations, 4,204 trains)
to power offline autocompletion and validation in ticket booking profiles.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional


class MasterDataService:
    """Service providing offline railway stations and trains lookup."""

    _instance: Optional[MasterDataService] = None

    def __init__(self, data_dir: Optional[str] = None) -> None:
        """Initialize the master data service.

        Args:
            data_dir: Path to directory containing stations.json and trains.json.
        """
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self._data_dir = data_dir

        self._stations: list[dict[str, Any]] = []
        self._stations_by_code: dict[str, dict[str, Any]] = {}
        self._station_completions: list[str] = []

        self._trains: list[dict[str, str]] = []
        self._trains_by_number: dict[str, dict[str, str]] = {}
        self._train_completions: list[str] = []

        self._loaded: bool = False
        self._load_data()

    def _load_data(self) -> None:
        """Load stations and trains datasets from disk."""
        if self._loaded:
            return

        # 1. Load stations
        stations_path = os.path.join(self._data_dir, "stations.json")
        if os.path.exists(stations_path):
            try:
                with open(stations_path, "r", encoding="utf-8") as f:
                    raw_stations = json.load(f)
                if isinstance(raw_stations, list):
                    self._stations = raw_stations
                    for s in raw_stations:
                        code = s.get("code", "").upper().strip()
                        name = s.get("name", "").strip()
                        if code:
                            self._stations_by_code[code] = s
                            self._station_completions.append(f"{code} - {name}")
            except Exception:
                pass

        # 2. Load trains
        trains_path = os.path.join(self._data_dir, "trains.json")
        if os.path.exists(trains_path):
            try:
                with open(trains_path, "r", encoding="utf-8") as f:
                    raw_trains = json.load(f)
                if isinstance(raw_trains, list):
                    for item in raw_trains:
                        if isinstance(item, str) and " - " in item:
                            parts = item.split(" - ", 1)
                            number = parts[0].strip()
                            name = parts[1].strip()
                            obj = {"number": number, "name": name, "display": item.strip()}
                            self._trains.append(obj)
                            self._trains_by_number[number] = obj
                            self._train_completions.append(item.strip())
            except Exception:
                pass

        self._loaded = True

    # ------------------------------------------------------------------
    # Station Lookups
    # ------------------------------------------------------------------

    @property
    def total_stations(self) -> int:
        """Return total loaded stations count."""
        return len(self._stations)

    def get_station_by_code(self, code: str) -> Optional[dict[str, Any]]:
        """Return station details by station code.

        Args:
            code: Station code (e.g., 'NDLS', 'HWH').

        Returns:
            Station dictionary or None.
        """
        return self._stations_by_code.get(code.upper().strip())

    def search_stations(self, query: str, limit: int = 15) -> list[dict[str, Any]]:
        """Search stations matching query in code or name.

        Args:
            query: Search string.
            limit: Maximum results to return.

        Returns:
            List of matching station dictionaries.
        """
        q = query.upper().strip()
        if not q:
            return []

        results: list[dict[str, Any]] = []
        # Prefix matches on code first
        for code, s in self._stations_by_code.items():
            if code.startswith(q):
                results.append(s)
                if len(results) >= limit:
                    return results

        # Substring matches on name
        for s in self._stations:
            if s in results:
                continue
            name = s.get("name", "").upper()
            if q in name:
                results.append(s)
                if len(results) >= limit:
                    break

        return results

    def get_station_completions(self) -> list[str]:
        """Return list of station formatted strings for QCompleter."""
        return self._station_completions

    # ------------------------------------------------------------------
    # Train Lookups
    # ------------------------------------------------------------------

    @property
    def total_trains(self) -> int:
        """Return total loaded trains count."""
        return len(self._trains)

    def get_train_by_number(self, number: str) -> Optional[dict[str, str]]:
        """Return train info by train number.

        Args:
            number: Train number (e.g., '12438', '12301').

        Returns:
            Train dictionary or None.
        """
        return self._trains_by_number.get(number.strip())

    def search_trains(self, query: str, limit: int = 15) -> list[dict[str, str]]:
        """Search trains matching query in number or name.

        Args:
            query: Train number or train name.
            limit: Maximum results.

        Returns:
            List of matching train dictionaries.
        """
        q = query.upper().strip()
        if not q:
            return []

        results: list[dict[str, str]] = []
        for t in self._trains:
            if t["number"].startswith(q) or q in t["name"].upper():
                results.append(t)
                if len(results) >= limit:
                    break
        return results

    def get_train_completions(self) -> list[str]:
        """Return list of train formatted strings for QCompleter."""
        return self._train_completions
