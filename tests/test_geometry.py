"""Exact-parity tests for the optics/geometry core.

The specification for this rewrite is "produce the same results as the original
program". The GOLDEN_* values below are therefore the outputs captured by
running the ORIGINAL project's pure calculation modules against the very
calibration file and height committed in this repo — i.e. an authoritative
reference implementation, not this code's own output. If a refactor ever changes
a number, these tests fail, which is exactly what "exactly the same" requires.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from linescan.calibration import load_calibration
from linescan.config import CameraConfig
from linescan.geometry import (
    compute_ground_sampling,
    compute_optical_parameters,
    pixel_distance_mm,
)
from linescan.state import load_height_mm

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CALIBRATION_FILE = DATA_DIR / "calibration" / "chessboard_calibration.npz"
HEIGHT_FILE = DATA_DIR / "state" / "height_mm.npy"

# --- Golden values captured from the original program (see module docstring) ---
GOLDEN_HEIGHT_MM = 191.44999235868454
GOLDEN_FOCAL_H_MM = 1.9521706833465766
GOLDEN_FOCAL_V_MM = 1.9458960235984006
GOLDEN_CENTER_X = 621.5922220082656
GOLDEN_CENTER_Y = 364.15162064800637
GOLDEN_PIXEL_PITCH_MM = 0.003
GOLDEN_HALF_WIDTH_MM = 188.29500333368938
GOLDEN_HALF_HEIGHT_MM = 106.25747174559838
GOLDEN_MM_PER_PIXEL_H = 0.29421874999998326
GOLDEN_MM_PER_PIXEL_V = 0.295277777777761
GOLDEN_OBSERVABLE_PLANE = "376.59 x 212.51"
# pixel_distance_mm(x2, x1, y2, y1) for two fixed point pairs.
GOLDEN_DISTANCE_CASE1 = 32.91837091411054  # (100, 0, 50, 0)
GOLDEN_DISTANCE_CASE2 = 212.94484755718665  # (640, 10, 360, 5)


@pytest.fixture(scope="module")
def config() -> CameraConfig:
    return CameraConfig()


@pytest.fixture(scope="module")
def calibration():
    return load_calibration(CALIBRATION_FILE)


def test_committed_height_matches_reference():
    assert load_height_mm(HEIGHT_FILE) == GOLDEN_HEIGHT_MM


def test_optical_parameters_match_original(config, calibration):
    optics = compute_optical_parameters(calibration, config)
    assert optics.pixel_pitch_h_mm == pytest.approx(GOLDEN_PIXEL_PITCH_MM, abs=1e-12)
    assert optics.pixel_pitch_v_mm == pytest.approx(GOLDEN_PIXEL_PITCH_MM, abs=1e-12)
    assert optics.focal_length_h_mm == pytest.approx(GOLDEN_FOCAL_H_MM, abs=1e-12)
    assert optics.focal_length_v_mm == pytest.approx(GOLDEN_FOCAL_V_MM, abs=1e-12)
    assert optics.optical_center_x == pytest.approx(GOLDEN_CENTER_X, abs=1e-12)
    assert optics.optical_center_y == pytest.approx(GOLDEN_CENTER_Y, abs=1e-12)


def test_ground_sampling_matches_original(config, calibration):
    optics = compute_optical_parameters(calibration, config)
    ground = compute_ground_sampling(optics, config, GOLDEN_HEIGHT_MM)

    assert ground.half_width_mm == pytest.approx(GOLDEN_HALF_WIDTH_MM, abs=1e-9)
    assert ground.half_height_mm == pytest.approx(GOLDEN_HALF_HEIGHT_MM, abs=1e-9)
    # mm-per-pixel must be bit-identical: it drives every real-world measurement.
    assert ground.mm_per_pixel_h == GOLDEN_MM_PER_PIXEL_H
    assert ground.mm_per_pixel_v == GOLDEN_MM_PER_PIXEL_V
    assert ground.observable_plane_label == GOLDEN_OBSERVABLE_PLANE


def test_pixel_distance_matches_original():
    # Same scales the original used at the working height.
    case1 = pixel_distance_mm(100, 0, 50, 0, GOLDEN_MM_PER_PIXEL_H, GOLDEN_MM_PER_PIXEL_V)
    case2 = pixel_distance_mm(640, 10, 360, 5, GOLDEN_MM_PER_PIXEL_H, GOLDEN_MM_PER_PIXEL_V)
    assert case1 == GOLDEN_DISTANCE_CASE1
    assert case2 == GOLDEN_DISTANCE_CASE2


def test_pixel_distance_is_symmetric_and_zero_at_same_point():
    a = pixel_distance_mm(10, 4, 8, 1, 0.3, 0.3)
    b = pixel_distance_mm(4, 10, 1, 8, 0.3, 0.3)
    assert a == b
    assert pixel_distance_mm(5, 5, 7, 7, 0.3, 0.3) == 0.0
