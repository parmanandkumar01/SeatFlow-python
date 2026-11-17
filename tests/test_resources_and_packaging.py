"""Tests for resource resolution and packaging helpers."""

import os
from pathlib import Path
from seatflow.utils.resources import (
    get_asset_path,
    get_bundle_dir,
    get_data_dir,
    get_resource_path,
)


def test_bundle_dir_resolution():
    """Verify bundle directory points to existing directory containing project structure."""
    bundle_dir = get_bundle_dir()
    assert bundle_dir.is_dir()
    assert (bundle_dir / "src").is_dir() or (bundle_dir / "seatflow").is_dir()


def test_asset_path_resolution():
    """Verify asset loader finds logo.png."""
    logo_path = get_asset_path("logo.png")
    assert logo_path.is_file()
    assert logo_path.name == "logo.png"


def test_branding_asset_resolution():
    """Verify branding asset is resolved."""
    branding_path = get_asset_path("branding/SeatFlow Neon Train Logo.png")
    assert branding_path.is_file()


def test_data_dir_resolution():
    """Verify master data directory contains stations.json and trains.json."""
    data_dir = get_data_dir()
    assert data_dir.is_dir()
    assert (data_dir / "stations.json").is_file()
    assert (data_dir / "trains.json").is_file()


def test_spec_file_exists():
    """Verify packaging spec file is configured properly."""
    spec_path = Path(__file__).resolve().parent.parent / "packaging" / "SeatFlow.spec"
    assert spec_path.is_file()
    content = spec_path.read_text(encoding="utf-8")
    assert "Analysis" in content
    assert "seatflow" in content
    assert "datas=" in content
