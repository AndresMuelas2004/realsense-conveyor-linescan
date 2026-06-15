"""Persisted runtime state: camera height and the Hall sensor's latest readings.

These small files decouple the measurement tools from the capture pipeline: the
height tool writes ``height_mm.npy`` once, the Hall sensor writes ``belt_speed``
and ``photo_interval`` on every revolution, and other tools just read them.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def save_height_mm(path: Path, height_mm: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, height_mm)


def load_height_mm(path: Path) -> float:
    if not path.exists():
        raise FileNotFoundError(
            f"Camera height not found: {path}. Run `linescan measure-height` first."
        )
    return float(np.load(path))


def save_belt_speed(path: Path, speed_mm_s: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, v=speed_mm_s)


def load_belt_speed(path: Path) -> float:
    return float(np.load(path)["v"])


def save_photo_interval(path: Path, interval_s: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, t=interval_s)


def load_photo_interval(path: Path) -> float:
    return float(np.load(path)["t"])
