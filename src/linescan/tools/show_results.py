"""Print the computed parameters for the current calibration and height.

Port of ``MOSTRAR_RESULTADOS``. A read-only sanity check (no camera needed):
it shows the operator-entered values alongside everything the system derives —
focal lengths, mm-per-pixel and the observable plane — so they can be eyeballed
before a capture run.
"""

from __future__ import annotations

from ..calibration import CameraCalibration
from ..config import CameraConfig
from ..geometry import GroundSampling, compute_optical_parameters


def show_results(
    config: CameraConfig, calibration: CameraCalibration, ground: GroundSampling
) -> dict[str, object]:
    """Print and return the computed parameters, rounded to two decimals."""
    optics = compute_optical_parameters(calibration, config)
    height_m = round(ground.height_mm / 1000, 2)

    results: dict[str, object] = {
        "Camera-measured height (mm)": round(ground.height_mm, 2),
        "Horizontal sensor (mm)": round(config.sensor_width_mm, 2),
        "Vertical sensor (mm)": round(config.sensor_height_mm, 2),
        "Horizontal FOV (deg)": round(config.fov_horizontal_deg, 2),
        "Vertical FOV (deg)": round(config.fov_vertical_deg, 2),
        "Horizontal focal length (mm)": round(optics.focal_length_h_mm, 2),
        "Vertical focal length (mm)": round(optics.focal_length_v_mm, 2),
        f"mm per horizontal pixel at {height_m} m": round(ground.mm_per_pixel_h, 2),
        f"mm per vertical pixel at {height_m} m": round(ground.mm_per_pixel_v, 2),
        "Observable plane at that height": ground.observable_plane_label,
    }

    print(" -- Values rounded to two decimals -- ")
    for key, value in results.items():
        print(key, f" = {value}")
    return results
