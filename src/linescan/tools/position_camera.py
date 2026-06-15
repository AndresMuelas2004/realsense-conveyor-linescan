"""Level the camera over the belt by comparing symmetric depth readings.

Port of ``POSICIONAR_CAMARA``. It prints the depth at four points equidistant
from the optical center — two on the vertical axis, two on the horizontal one.
If the camera is parallel to the belt, each pair should read (nearly) the same;
less than ~1 mm of difference per pair over ten prints means it is well placed.
Run it over the belt under good lighting.
"""

from __future__ import annotations

import time

from ..calibration import CameraCalibration
from ..camera import RealSenseCamera
from ..config import CameraConfig
from ..keys import quit_pressed

# Symmetric offsets from the optical center used to check leveling.
VERTICAL_OFFSET_PX = 330
HORIZONTAL_OFFSET_PX = 500
PRINT_PERIOD_S = 1.0


def position_camera(config: CameraConfig, calibration: CameraCalibration) -> None:
    """Print symmetric depth readings once per second until 'q'."""
    cx, cy = calibration.cx, calibration.cy
    with RealSenseCamera(config) as camera:
        camera.start(color=False, depth=True)
        last_print = time.time()
        while not quit_pressed():
            if time.time() - last_print < PRINT_PERIOD_S:
                continue
            depth = camera.depth_frame(camera.wait_frames())
            if depth is None:
                continue
            print("____________________________________________________________________")
            print(f" VVV --- {camera.distance_mm(depth, cx, cy + VERTICAL_OFFSET_PX)}")
            print(f" VVV --- {camera.distance_mm(depth, cx, cy - VERTICAL_OFFSET_PX)}")
            print(f" HHH --- {camera.distance_mm(depth, cx + HORIZONTAL_OFFSET_PX, cy)}")
            print(f" HHH --- {camera.distance_mm(depth, cx - HORIZONTAL_OFFSET_PX, cy)}")
            last_print = time.time()
