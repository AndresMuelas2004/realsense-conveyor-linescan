"""Loading intrinsic calibration and the accessors derived from it.

``load_calibration`` reads the ``.npz`` (keys ``mtx``/``dist``/``ret``) the
chessboard session produces; the ``fx``/``fy``/``cx``/``cy`` properties pull the
focal lengths and optical center out of the 3x3 intrinsic matrix. A missing file
must raise loudly so a station never runs uncalibrated.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from linescan.calibration import CameraCalibration, load_calibration

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CALIBRATION_FILE = DATA_DIR / "calibration" / "chessboard_calibration.npz"


def test_load_calibration_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_calibration(tmp_path / "missing.npz")


def test_load_calibration_round_trips_a_written_file(tmp_path):
    matrix = np.array(
        [[650.0, 0.0, 620.0], [0.0, 648.0, 360.0], [0.0, 0.0, 1.0]], dtype=np.float64
    )
    dist = np.array([[-0.04, 0.05, 0.0002, -0.0006, -0.013]], dtype=np.float64)
    path = tmp_path / "calib.npz"
    np.savez(path, mtx=matrix, dist=dist, ret=0.5)

    calibration = load_calibration(path)

    assert isinstance(calibration, CameraCalibration)
    np.testing.assert_array_equal(calibration.intrinsic_matrix, matrix)
    np.testing.assert_array_equal(calibration.distortion_coeffs, dist)
    assert calibration.reprojection_error == 0.5
    assert isinstance(calibration.reprojection_error, float)


def test_intrinsic_accessors_map_to_matrix_cells():
    matrix = np.array(
        [[650.0, 0.0, 620.0], [0.0, 648.0, 360.0], [0.0, 0.0, 1.0]], dtype=np.float64
    )
    calibration = CameraCalibration(
        intrinsic_matrix=matrix,
        distortion_coeffs=np.zeros((1, 5)),
        reprojection_error=0.0,
    )
    # fx/fy on the diagonal, cx/cy in the third column.
    assert calibration.fx == 650.0
    assert calibration.fy == 648.0
    assert calibration.cx == 620.0
    assert calibration.cy == 360.0
    accessors = (calibration.fx, calibration.fy, calibration.cx, calibration.cy)
    assert all(isinstance(v, float) for v in accessors)


def test_committed_example_file_loads_expected_intrinsics():
    # Values read directly from the committed example .npz (the authoritative
    # reference the golden geometry tests are also derived from).
    calibration = load_calibration(CALIBRATION_FILE)
    assert calibration.fx == pytest.approx(650.7235611, abs=1e-6)
    assert calibration.fy == pytest.approx(648.6320079, abs=1e-6)
    assert calibration.cx == pytest.approx(621.5922220, abs=1e-6)
    assert calibration.cy == pytest.approx(364.1516206, abs=1e-6)
    assert calibration.reprojection_error == pytest.approx(0.4590611, abs=1e-6)
    assert calibration.distortion_coeffs.shape == (1, 5)
