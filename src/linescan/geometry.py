"""Pure optics/geometry: the numeric core of the system.

Every function here is deterministic and hardware-free, which is why it is the
part covered by exact-parity unit tests (``tests/test_geometry.py``). The
formulas reproduce the original project bit-for-bit; where the original relied
on an implementation quirk that affects the result, it is reproduced on purpose
and called out in a comment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # avoid a runtime import cycle; only attributes fx/fy/cx/cy are used
    from .calibration import CameraCalibration
    from .config import CameraConfig

# Step (mm) at which the original code sampled the ground plane to size a pixel.
# The reconstruction's mm-per-pixel is derived from this grid (see note below).
GROUND_GRID_STEP_MM = 0.1


@dataclass(frozen=True)
class OpticalParameters:
    """Per-camera optics derived from the intrinsic calibration and pixel size."""

    pixel_pitch_h_mm: float
    pixel_pitch_v_mm: float
    focal_length_h_mm: float
    focal_length_v_mm: float
    optical_center_x: float
    optical_center_y: float
    fx_pixels: float
    fy_pixels: float


@dataclass(frozen=True)
class GroundSampling:
    """How the ground plane maps to pixels at a specific camera height.

    ``half_width_mm`` / ``half_height_mm`` are the half-extents of the area the
    camera sees on a plane at ``height_mm`` (the original ``Real_Inicial_hor`` /
    ``Real_Inicial_ver``). ``mm_per_pixel_*`` converts pixel distances on a
    reconstruction into real-world millimetres.
    """

    height_mm: float
    half_width_mm: float
    half_height_mm: float
    mm_per_pixel_h: float
    mm_per_pixel_v: float

    @property
    def observable_plane_mm(self) -> tuple[float, float]:
        """Full (width, height) in mm of the plane the camera observes."""
        return (abs(round(self.half_width_mm * 2, 2)), abs(round(self.half_height_mm * 2, 2)))

    @property
    def observable_plane_label(self) -> str:
        """Human-readable ``"W x H"`` label (matches the original output)."""
        w, h = self.observable_plane_mm
        return f"{w} x {h}"


def compute_optical_parameters(
    calibration: CameraCalibration, config: CameraConfig
) -> OpticalParameters:
    """Derive pixel pitch, focal length (mm) and optical center from calibration.

    Focal length in mm = focal length in pixels (from the intrinsic matrix) times
    the physical pixel pitch.
    """
    pixel_pitch_h = config.sensor_width_mm / config.width_px
    pixel_pitch_v = config.sensor_height_mm / config.height_px
    return OpticalParameters(
        pixel_pitch_h_mm=pixel_pitch_h,
        pixel_pitch_v_mm=pixel_pitch_v,
        focal_length_h_mm=calibration.fx * pixel_pitch_h,
        focal_length_v_mm=calibration.fy * pixel_pitch_v,
        optical_center_x=calibration.cx,
        optical_center_y=calibration.cy,
        fx_pixels=calibration.fx,
        fy_pixels=calibration.fy,
    )


def _captured_span_mm(half_extent_mm: float) -> float:
    """Span (mm) the original code measured across one axis of the ground plane.

    Faithful reproduction: the original built a coordinate grid with
    ``numpy.arange(-half, half + step, step)`` and summed the absolute values of
    its first and last samples. Because ``half`` is not a multiple of ``step``,
    the grid overshoots ``half`` by up to one step on the high side, so the span
    is *not* exactly ``2 * half``. Reproducing this keeps mm-per-pixel identical
    to the original to the last digit. (A clean ``2 * half_extent_mm`` would
    differ only around the 5th significant figure — sub-micron per pixel.)
    """
    axis = np.arange(-half_extent_mm, half_extent_mm + GROUND_GRID_STEP_MM, GROUND_GRID_STEP_MM)
    return float(abs(axis[0]) + abs(axis[-1]))


def compute_ground_sampling(
    optics: OpticalParameters, config: CameraConfig, height_mm: float
) -> GroundSampling:
    """Compute the observable plane and mm-per-pixel at a given camera height.

    Uses similar triangles: the half-extent on the ground equals the sensor
    half-size scaled by ``height / focal_length``.
    """
    half_width = (config.sensor_width_mm / 2) * height_mm / optics.focal_length_h_mm
    half_height = (config.sensor_height_mm / 2) * height_mm / optics.focal_length_v_mm

    mm_per_pixel_h = _captured_span_mm(half_width) / config.width_px
    mm_per_pixel_v = _captured_span_mm(half_height) / config.height_px

    return GroundSampling(
        height_mm=height_mm,
        half_width_mm=half_width,
        half_height_mm=half_height,
        mm_per_pixel_h=mm_per_pixel_h,
        mm_per_pixel_v=mm_per_pixel_v,
    )


def pixel_distance_mm(
    x2: float,
    x1: float,
    y2: float,
    y1: float,
    mm_per_pixel_h: float,
    mm_per_pixel_v: float,
) -> float:
    """Real-world distance (mm) between two pixels on a reconstruction.

    Horizontal and vertical pixel gaps are scaled independently (the scales
    differ) and combined with the Euclidean norm.
    """
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    # Explicit sqrt of the sum of squares (not math.hypot) to stay bit-identical
    # to the original expression ``(...**2 + ...**2) ** 0.5``.
    return ((dx * mm_per_pixel_h) ** 2 + (dy * mm_per_pixel_v) ** 2) ** 0.5
