"""Round-trips and load-error behavior of the persisted runtime state.

These small ``.npy``/``.npz`` files decouple the tools from the capture loop.
The contract that matters: every value written must read back as a plain
``float``, missing files must raise (so a misconfigured station fails loudly
rather than silently using a stale or zero value), and ``save_*`` must create
the parent directory on demand.
"""

from __future__ import annotations

import numpy as np
import pytest

from linescan.state import (
    load_belt_speed,
    load_height_mm,
    load_photo_interval,
    save_belt_speed,
    save_height_mm,
    save_photo_interval,
)


def test_height_round_trips_as_float(tmp_path):
    path = tmp_path / "height_mm.npy"
    save_height_mm(path, 191.45)
    loaded = load_height_mm(path)
    assert loaded == 191.45
    assert isinstance(loaded, float)


def test_save_height_creates_missing_parent_directory(tmp_path):
    path = tmp_path / "nested" / "state" / "height_mm.npy"
    save_height_mm(path, 12.5)
    assert path.exists()
    assert load_height_mm(path) == 12.5


def test_load_height_raises_with_actionable_message_when_missing(tmp_path):
    path = tmp_path / "missing.npy"
    with pytest.raises(FileNotFoundError) as exc:
        load_height_mm(path)
    # The message must point the operator at the tool that produces the file.
    assert "measure-height" in str(exc.value)


def test_belt_speed_round_trips_as_float(tmp_path):
    path = tmp_path / "belt_speed.npz"
    save_belt_speed(path, 123.75)
    loaded = load_belt_speed(path)
    assert loaded == 123.75
    assert isinstance(loaded, float)


def test_photo_interval_round_trips_as_float(tmp_path):
    path = tmp_path / "photo_interval.npz"
    save_photo_interval(path, 0.0334)
    loaded = load_photo_interval(path)
    assert loaded == pytest.approx(0.0334)
    assert isinstance(loaded, float)


def test_save_belt_speed_creates_missing_parent_directory(tmp_path):
    path = tmp_path / "nested" / "belt_speed.npz"
    save_belt_speed(path, 1.0)
    assert path.exists()


def test_load_belt_speed_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_belt_speed(tmp_path / "missing.npz")


def test_load_photo_interval_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_photo_interval(tmp_path / "missing.npz")


def test_load_belt_speed_raises_on_wrong_key(tmp_path):
    # belt-speed is stored under key "v"; an archive without it must not be
    # silently accepted as a valid reading.
    path = tmp_path / "wrong.npz"
    np.savez(path, t=1.0)
    with pytest.raises(KeyError):
        load_belt_speed(path)
