#!/usr/bin/env python3
"""Build automation script for compiling SeatFlow into a standalone executable.

Usage:
    python packaging/build_binary.py [--onefile] [--clean] [--verify]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = PROJECT_ROOT / "packaging" / "SeatFlow.spec"


def check_prerequisites() -> bool:
    """Ensure PyInstaller and required build tools are installed."""
    try:
        import PyInstaller
        print(f"✓ PyInstaller version {PyInstaller.__version__} detected.")
        return True
    except ImportError:
        print("✗ PyInstaller is not installed in the current Python environment.")
        print("  To install: pip install pyinstaller")
        return False


def build(onefile: bool = False, clean: bool = True) -> int:
    """Run PyInstaller build."""
    if not check_prerequisites():
        return 1

    build_dir = PROJECT_ROOT / "build"
    dist_dir = PROJECT_ROOT / "dist"

    if clean:
        print(f"→ Cleaning build directory {build_dir} and dist directory {dist_dir}...")
        if build_dir.exists():
            shutil.rmtree(build_dir, ignore_errors=True)
        if dist_dir.exists():
            shutil.rmtree(dist_dir, ignore_errors=True)

    env = os.environ.copy()
    env["SEATFLOW_BUILD_ONEFILE"] = "1" if onefile else "0"
    mode_str = "Single-file standalone binary (--onefile)" if onefile else "Directory bundle (--onedir)"

    print(f"\n==========================================")
    print(f"  Building SeatFlow Executable")
    print(f"  Mode: {mode_str}")
    print(f"  Spec: {SPEC_FILE}")
    print(f"==========================================\n")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        str(SPEC_FILE),
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
    ]

    result = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env)
    if result.returncode != 0:
        print("\n✗ Build failed! Check PyInstaller output above.")
        return result.returncode

    print("\n==========================================")
    print("✓ SeatFlow Build Complete!")
    if onefile:
        binary_path = dist_dir / "SeatFlow"
        if binary_path.exists():
            size_mb = binary_path.stat().st_size / (1024 * 1024)
            print(f"  Binary: {binary_path} ({size_mb:.1f} MB)")
    else:
        bundle_path = dist_dir / "SeatFlow"
        print(f"  Bundle Directory: {bundle_path}")
    print("==========================================\n")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile SeatFlow application into standalone executable.")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build a single standalone binary file instead of a directory bundle.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not clean build/ and dist/ directories before building.",
    )
    args = parser.parse_args()

    code = build(onefile=args.onefile, clean=not args.no_clean)
    sys.exit(code)


if __name__ == "__main__":
    main()
