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
    GroundSampling,
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


def test_pixel_distance_uses_per_axis_scales_independently():
    # A purely horizontal gap is scaled only by the horizontal pitch, and a
    # purely vertical gap only by the vertical pitch (the two scales differ).
    assert pixel_distance_mm(10, 0, 5, 5, 0.5, 0.2) == pytest.approx(10 * 0.5)
    assert pixel_distance_mm(5, 5, 10, 0, 0.5, 0.2) == pytest.approx(10 * 0.2)


def test_observable_plane_doubles_half_extents_and_rounds_to_two_decimals():
    # observable_plane_mm = (round(2*half_width, 2), round(2*half_height, 2)).
    ground = GroundSampling(
        height_mm=100.0,
        half_width_mm=188.295003,
        half_height_mm=106.257471,
        mm_per_pixel_h=0.1,
        mm_per_pixel_v=0.1,
    )
    assert ground.observable_plane_mm == (376.59, 212.51)
    assert ground.observable_plane_label == "376.59 x 212.51"


def test_observable_plane_is_absolute_valued():
    # Half-extents can come out negative depending on calibration sign; the
    # reported plane is always positive (the original applied abs()).
    ground = GroundSampling(
        height_mm=100.0,
        half_width_mm=-50.0,
        half_height_mm=-25.0,
        mm_per_pixel_h=0.1,
        mm_per_pixel_v=0.1,
    )
    assert ground.observable_plane_mm == (100.0, 50.0)


def test_ground_sampling_scales_linearly_with_height(config, calibration):
    # Half-extents come from similar triangles, so doubling the height doubles
    # the observed half-width/half-height.
    optics = compute_optical_parameters(calibration, config)
    base = compute_ground_sampling(optics, config, 100.0)
    taller = compute_ground_sampling(optics, config, 200.0)
    assert taller.half_width_mm == pytest.approx(2 * base.half_width_mm)
    assert taller.half_height_mm == pytest.approx(2 * base.half_height_mm)


def test_mm_per_pixel_is_positive_and_close_to_two_half_extents(config, calibration):
    # The captured-span quirk overshoots 2*half by less than one 0.1 mm grid step
    # per axis, so mm-per-pixel stays within that span / pixel-count of the clean
    # value. This pins the documented "sub-micron" effect without re-deriving it.
    optics = compute_optical_parameters(calibration, config)
    ground = compute_ground_sampling(optics, config, GOLDEN_HEIGHT_MM)

    clean_h = (2 * ground.half_width_mm) / config.width_px
    clean_v = (2 * ground.half_height_mm) / config.height_px
    assert ground.mm_per_pixel_h > 0
    assert ground.mm_per_pixel_v > 0
    assert abs(ground.mm_per_pixel_h - clean_h) < 0.1 / config.width_px
    assert abs(ground.mm_per_pixel_v - clean_v) < 0.1 / config.height_px
