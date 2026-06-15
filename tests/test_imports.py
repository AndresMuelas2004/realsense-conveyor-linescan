"""The whole package must import with no camera/serial hardware present.

A core design goal of the rewrite is that importing any module never pulls in
``pyrealsense2``/``serial``/``keyboard`` (the original ran hardware and file I/O
at import time). Importing every module here — including the hardware-facing
ones — proves those heavy dependencies stay lazy.
"""

from __future__ import annotations

import importlib

import pytest

import linescan

MODULES = [
    "linescan.config",
    "linescan.geometry",
    "linescan.calibration",
    "linescan.state",
    "linescan.camera",
    "linescan.hall_sensor",
    "linescan.reconstruction",
    "linescan.capture",
    "linescan.measurement",
    "linescan.report",
    "linescan.archive",
    "linescan.keys",
    "linescan.cli",
    "linescan.tools",
]


def test_version_is_exposed():
    assert linescan.__version__ == "1.0.0"


def test_all_modules_import_without_hardware():
    for name in MODULES:
        importlib.import_module(name)


def test_config_defaults_reproduce_the_original_rig():
    from linescan.config import CameraConfig

    config = CameraConfig()
    # Sensor size is derived from pixel count x pixel pitch (1280x720 @ 0.003 mm).
    assert config.sensor_width_mm == pytest.approx(3.84)
    assert config.sensor_height_mm == pytest.approx(2.16)


def test_storage_layout_paths_are_relative_to_base_dir(tmp_path):
    from linescan.config import StorageLayout

    storage = StorageLayout(base_dir=tmp_path, data_dir=tmp_path / "data")
    assert storage.reconstructions_dir == tmp_path / "reconstructions"
    assert storage.strip_dir_for(3) == tmp_path / "strips" / "IR3"
    assert storage.calibration_file == tmp_path / "data" / "calibration" / "chessboard_calibration.npz"
