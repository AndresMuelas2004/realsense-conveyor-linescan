"""Measure the camera height above the surface under the optical center.

Port of ``MEDIR_ALTURA``. Takes the median of 100 depth readings (each after
discarding a few frames to let the depth settle) for robustness, then persists
it so the rest of the system can derive mm-per-pixel without re-measuring.
Place the part's top surface under the camera and measure the distance to it.
"""

from __future__ import annotations

import statistics

from ..calibration import CameraCalibration
from ..camera import RealSenseCamera
from ..config import CameraConfig, StorageLayout
from ..state import save_height_mm

HEIGHT_SAMPLES = 100
FRAMES_PER_SAMPLE = 10  # frames discarded before each kept reading


def measure_height(
    config: CameraConfig, calibration: CameraCalibration, storage: StorageLayout
) -> float:
    """Measure, persist and return the camera height in millimetres."""
    cx, cy = calibration.cx, calibration.cy
    samples: list[float] = []
    with RealSenseCamera(config) as camera:
        camera.start(color=False, depth=True)
        for i in range(HEIGHT_SAMPLES):
            frames = camera.wait_frames()
            for _ in range(FRAMES_PER_SAMPLE - 1):
                frames = camera.wait_frames()
            distance = camera.distance_mm(camera.depth_frame(frames), cx, cy)
            samples.append(distance)
            print(f"Height {i + 1}: {distance}")

    height_mm = statistics.median(samples)
    print(height_mm)
    save_height_mm(storage.height_file, height_mm)
    return height_mm
