"""Resource resolution utilities for development and compiled binary distributions (PyInstaller/Nuitka/AppImage)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


def get_bundle_dir() -> Path:
    """Return the base directory for bundled application assets.
    
    Supports:
    - PyInstaller onefile: sys._MEIPASS
    - PyInstaller onedir / Nuitka: directory containing the executable
    - AppImage: $APPDIR
    - Development mode: project root directory containing src/
    """
    # 1. PyInstaller temporary extraction directory (onefile mode)
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)

    # 2. Linux AppImage runtime environment
    appdir = os.environ.get("APPDIR")
    if appdir and os.path.isdir(appdir):
        return Path(appdir) / "usr" / "share" / "seatflow"

    # 3. Frozen executable directory (onedir mode)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    # 4. Standard Python development mode: walk up from this file to find project root
    # resources.py -> utils -> seatflow -> src -> SeatFlow (project root)
    return Path(__file__).resolve().parent.parent.parent.parent


def get_resource_path(relative_path: str) -> Path:
    """Resolve an absolute path to a resource file.
    
    Searches both inside the bundled bundle dir and standard project locations.
    """
    base = get_bundle_dir()
    
    # Direct relative match
    candidate = base / relative_path
    if candidate.exists():
        return candidate

    # If relative_path starts with 'assets/' or 'data/'
    # Check under src/seatflow/ for package data
    candidate_pkg = base / "seatflow" / relative_path
    if candidate_pkg.exists():
        return candidate_pkg

    # Check under src/
    candidate_src = base / "src" / "seatflow" / relative_path
    if candidate_src.exists():
        return candidate_src

    # Fallback to current working directory
    cwd_candidate = Path.cwd() / relative_path
    if cwd_candidate.exists():
        return cwd_candidate

    return candidate


def get_asset_path(filename: str) -> Path:
    """Resolve an asset file path (e.g. 'logo.png', 'branding/SeatFlow Neon Train Logo.png')."""
    return get_resource_path(f"assets/{filename}")


def get_data_dir() -> Path:
    """Resolve directory containing stations.json and trains.json master datasets."""
    # 1. Check bundled seatflow/data
    base = get_bundle_dir()
    candidates = [
        base / "seatflow" / "data",
        base / "data",
        base / "src" / "seatflow" / "data",
        Path(__file__).resolve().parent.parent / "data",
    ]
    for c in candidates:
        if c.is_dir() and (c / "stations.json").exists():
            return c

    # Fallback default
    return Path(__file__).resolve().parent.parent / "data"
