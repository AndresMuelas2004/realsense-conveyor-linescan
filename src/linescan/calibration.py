"""Camera intrinsic calibration: load a saved one, or run a chessboard session.

The intrinsic matrix and distortion coefficients are obtained once per camera
with the classic OpenCV chessboard method and stored in a ``.npz`` (keys
``mtx`` / ``dist`` / ``ret``). Every downstream calculation only needs to *load*
that file, which is fast and hardware-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .camera import RealSenseCamera
from .config import CameraConfig

# Default chessboard used for the original camera. Inner corners, not squares.
DEFAULT_PATTERN_SIZE = (8, 5)
DEFAULT_SQUARE_SIZE_MM = 27.0
_CORNER_REFINE_CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)


@dataclass(frozen=True)
class CameraCalibration:
    """Intrinsic calibration of a single camera."""

    intrinsic_matrix: np.ndarray  # 3x3
    distortion_coeffs: np.ndarray  # (1, 5)
    reprojection_error: float  # mean reprojection error returned by calibrateCamera

    @property
    def fx(self) -> float:
        return float(self.intrinsic_matrix[0][0])

    @property
    def fy(self) -> float:
        return float(self.intrinsic_matrix[1][1])

    @property
    def cx(self) -> float:
        return float(self.intrinsic_matrix[0][2])

    @property
    def cy(self) -> float:
        return float(self.intrinsic_matrix[1][2])


def load_calibration(path: Path) -> CameraCalibration:
    """Load a calibration ``.npz`` (keys ``mtx``, ``dist``, ``ret``)."""
    if not path.exists():
        raise FileNotFoundError(f"Calibration file not found: {path}")
    data = np.load(path)
    return CameraCalibration(
        intrinsic_matrix=data["mtx"],
        distortion_coeffs=data["dist"],
        reprojection_error=float(data["ret"]),
    )


def run_chessboard_calibration(
    config: CameraConfig,
    output_path: Path,
    image_dir: Path,
    *,
    pattern_size: tuple[int, int] = DEFAULT_PATTERN_SIZE,
    square_size_mm: float = DEFAULT_SQUARE_SIZE_MM,
) -> CameraCalibration | None:
    """Interactively capture chessboard views and compute the intrinsics.

    Run this only when (re)deploying a camera. Show the printed chessboard at
    many angles/distances, press ``s`` to grab each view (~20+ is good), then
    ``q`` to calibrate. The result is saved to ``output_path`` and returned;
    returns ``None`` if no view contained a detectable pattern.
    """
    image_dir.mkdir(parents=True, exist_ok=True)
    print("Press 's' to save a view | 'q' to finish and calibrate")

    saved = _capture_chessboard_views(config, image_dir)
    object_points, image_points, image_shape = _find_corners(image_dir, pattern_size, square_size_mm)

    if not object_points or image_shape is None:
        print("The chessboard was not detected in any view; nothing to calibrate.")
        return None

    # cameraMatrix/distCoeffs are None so OpenCV estimates them from scratch (the
    # documented usage); the type stubs do not model that overload, hence ignore.
    reproj_error, matrix, distortion, _, _ = cv2.calibrateCamera(
        object_points, image_points, image_shape, None, None
    )  # type: ignore[call-overload]
    print("Intrinsic matrix:\n", matrix)
    print("Distortion coefficients:\n", distortion)
    print("Mean reprojection error:\n", reproj_error)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(output_path, mtx=matrix, dist=distortion, ret=reproj_error)
    print(f"Saved calibration to {output_path} ({saved} views captured)")
    return CameraCalibration(matrix, distortion, float(reproj_error))


def _capture_chessboard_views(config: CameraConfig, image_dir: Path) -> int:
    """Live preview; save the current color frame on 's', stop on 'q'."""
    saved = 0
    with RealSenseCamera(config) as camera:
        camera.start(color=True)
        while True:
            frames = camera.wait_frames()
            color = camera.color_frame(frames)
            if color is None:
                continue
            image = camera.to_image(color)
            cv2.imshow("RealSense", image)
            key = cv2.waitKey(1)
            if key == ord("s"):
                filename = image_dir / f"view_{saved}.jpg"
                cv2.imwrite(str(filename), image)
                print(f"Saved: {filename}")
                saved += 1
            elif key == ord("q"):
                break
    cv2.destroyAllWindows()
    return saved


def _find_corners(
    image_dir: Path, pattern_size: tuple[int, int], square_size_mm: float
) -> tuple[list[np.ndarray], list[np.ndarray], tuple[int, int] | None]:
    """Detect (and sub-pixel refine) chessboard corners across the saved views."""
    # Reference 3D coordinates of the chessboard corners (z = 0 plane), in mm.
    objp = np.zeros((pattern_size[0] * pattern_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0 : pattern_size[0], 0 : pattern_size[1]].T.reshape(-1, 2)
    objp *= square_size_mm

    object_points: list[np.ndarray] = []
    image_points: list[np.ndarray] = []
    image_shape: tuple[int, int] | None = None

    for image_path in sorted(image_dir.glob("*.jpg")):
        image = cv2.imread(str(image_path))
        if image is None:
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCorners(gray, pattern_size, None)
        if not found:
            continue
        image_shape = gray.shape[::-1]
        refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), _CORNER_REFINE_CRITERIA)
        object_points.append(objp)
        image_points.append(refined)

    return object_points, image_points, image_shape
