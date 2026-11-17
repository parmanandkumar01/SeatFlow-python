# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for SeatFlow Desktop Application.

Bundles all PySide6 runtime dependencies, SQLite, static railway master data,
branding assets, and dynamically discovered pluggable booking engines into a
standalone Linux / Windows binary distribution.
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Collect all engine implementations and services dynamically
hidden_imports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "sqlite3",
    "json",
    "hashlib",
    "hmac",
    "secrets",
    "seatflow",
    "seatflow.main",
    "seatflow.app",
    "seatflow.app.application",
    "seatflow.database.database",
    "seatflow.engines",
    "seatflow.engines.base",
    "seatflow.engines.events",
    "seatflow.engines.registry",
    "seatflow.engines.runner",
    "seatflow.engines.drivers.browser_driver",
    "seatflow.engines.drivers.http_driver",
]

for package_name in [
    "seatflow.engines",
    "seatflow.engines.implementations",
    "seatflow.engines.drivers",
    "seatflow.services",
    "seatflow.repositories",
    "seatflow.ui",
    "seatflow.ui.dialogs",
    "seatflow.ui.pages",
    "seatflow.ui.widgets",
    "seatflow.utils",
]:
    try:
        submods = collect_submodules(package_name)
        hidden_imports.extend(submods)
    except Exception:
        pass

# Bundle static assets and master railway data JSONs
datas = [
    (str(PROJECT_ROOT / "assets"), "assets"),
    (str(SRC_DIR / "seatflow" / "data"), "seatflow/data"),
    (str(SRC_DIR / "seatflow" / "integrations" / "host_manifest.json"), "seatflow/integrations"),
]

a = Analysis(
    [str(SRC_DIR / "seatflow" / "main.py")],
    pathex=[str(SRC_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=sorted(list(set(hidden_imports))),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pytest", "IPython", "notebook"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Check if onefile mode is requested via environment variable
ONEFILE = os.environ.get("SEATFLOW_BUILD_ONEFILE", "0") == "1"

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="SeatFlow",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(PROJECT_ROOT / "assets" / "logo.png"),
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="SeatFlow",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(PROJECT_ROOT / "assets" / "logo.png"),
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="SeatFlow",
    )
