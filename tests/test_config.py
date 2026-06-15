"""Behavior of the static configuration and the storage layout.

``CameraConfig`` derives the sensor size from the pixel count and pitch;
``StorageLayout`` is the single source of truth for every path the station
reads from or writes to, resolved from a base/data directory. These tests pin
the derived values and the path mapping (folder renames included), which a
refactor must not silently change.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from linescan.config import DEFAULT_DATA_DIR, PROJECT_ROOT, CameraConfig, StorageLayout


def test_sensor_size_is_pixel_count_times_pitch():
    config = CameraConfig()
    assert config.sensor_width_mm == pytest.approx(config.width_px * config.pixel_size_mm)
    assert config.sensor_height_mm == pytest.approx(config.height_px * config.pixel_size_mm)


def test_sensor_size_follows_overridden_pixel_dimensions():
    config = CameraConfig(width_px=640, height_px=480, pixel_size_mm=0.01)
    assert config.sensor_width_mm == pytest.approx(6.4)
    assert config.sensor_height_mm == pytest.approx(4.8)


def test_config_is_frozen():
    config = CameraConfig()
    with pytest.raises(FrozenInstanceError):
        config.width_px = 999  # type: ignore[misc]


def test_default_data_dir_is_under_project_root():
    assert DEFAULT_DATA_DIR == PROJECT_ROOT / "data"


def test_storage_layout_defaults_base_dir_to_cwd():
    storage = StorageLayout()
    assert storage.base_dir == Path.cwd()
    assert storage.data_dir == DEFAULT_DATA_DIR


def test_runtime_output_paths_are_under_base_dir(tmp_path):
    storage = StorageLayout(base_dir=tmp_path, data_dir=tmp_path / "data")
    assert storage.reconstructions_dir == tmp_path / "reconstructions"
    assert storage.strips_dir == tmp_path / "strips"
    assert storage.history_dir == tmp_path / "history"
    assert storage.parameter_log_file == tmp_path / "camera_parameters_log.json"


def test_state_and_calibration_paths_are_under_data_dir(tmp_path):
    data_dir = tmp_path / "data"
    storage = StorageLayout(base_dir=tmp_path, data_dir=data_dir)
    assert storage.calibration_file == data_dir / "calibration" / "chessboard_calibration.npz"
    assert storage.height_file == data_dir / "state" / "height_mm.npy"
    assert storage.belt_speed_file == data_dir / "state" / "belt_speed.npz"
    assert storage.photo_interval_file == data_dir / "state" / "photo_interval.npz"


def test_strip_dir_for_uses_ir_prefixed_index(tmp_path):
    storage = StorageLayout(base_dir=tmp_path, data_dir=tmp_path / "data")
    assert storage.strip_dir_for(1) == tmp_path / "strips" / "IR1"
    assert storage.strip_dir_for(42) == tmp_path / "strips" / "IR42"
