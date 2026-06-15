"""Error tolerance of the parameter-log helpers.

``write_parameter_log`` itself needs the camera, but ``_safe_load`` is pure: it
lets a run still be logged when an optional state file (belt speed / photo
interval) was never written, by returning ``None`` instead of raising. These
tests pin that fall-back and confirm a real value passes straight through.
"""

from __future__ import annotations

from linescan.report import _safe_load
from linescan.state import (
    load_belt_speed,
    load_photo_interval,
    save_belt_speed,
    save_photo_interval,
)


def test_safe_load_returns_none_when_file_missing(tmp_path):
    assert _safe_load(load_belt_speed, tmp_path / "missing.npz") is None
    assert _safe_load(load_photo_interval, tmp_path / "missing.npz") is None


def test_safe_load_returns_none_on_wrong_key(tmp_path):
    # photo_interval is stored under "t"; a belt-speed archive lacks it.
    path = tmp_path / "belt_speed.npz"
    save_belt_speed(path, 100.0)
    assert _safe_load(load_photo_interval, path) is None


def test_safe_load_passes_through_a_real_value(tmp_path):
    path = tmp_path / "photo_interval.npz"
    save_photo_interval(path, 0.0334)
    assert _safe_load(load_photo_interval, path) == 0.0334


def test_safe_load_propagates_loader_result_type(tmp_path):
    path = tmp_path / "belt_speed.npz"
    save_belt_speed(path, 42.0)
    result = _safe_load(load_belt_speed, path)
    assert isinstance(result, float)
    assert result == 42.0
