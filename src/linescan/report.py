"""Append a snapshot of every run parameter to a persistent log.

Called at the end of a capture run (port of the original ``FicheroJson``). It
records the values entered by the operator, the values computed by the system
and the intrinsics reported live by the SDK, so a run can always be traced back
to the exact configuration that produced it.

The log is written as JSON Lines (one self-contained JSON object per line) so it
stays append-only yet fully machine-readable — the original concatenated indented
objects, which was not valid JSON as a whole.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .calibration import CameraCalibration
from .camera import RealSenseCamera
from .config import CameraConfig, StorageLayout
from .geometry import GroundSampling
from .state import load_belt_speed, load_photo_interval

# Frames discarded so auto-exposure/white-balance settle before reading intrinsics.
WARMUP_FRAMES = 5


def write_parameter_log(
    config: CameraConfig,
    calibration: CameraCalibration,
    ground: GroundSampling,
    storage: StorageLayout,
) -> None:
    """Capture one frame for live intrinsics and append a parameter record."""
    with RealSenseCamera(config) as camera:
        camera.start(color=True)
        camera.warmup(WARMUP_FRAMES)
        intrinsics = camera.color_intrinsics()
        exposure_ms = float(camera.exposure_raw() / 1000)

    record = _build_record(config, calibration, ground, intrinsics, exposure_ms, storage)
    storage.parameter_log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(storage.parameter_log_file, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _build_record(
    config: CameraConfig,
    calibration: CameraCalibration,
    ground: GroundSampling,
    intrinsics: Any,
    exposure_ms: float,
    storage: StorageLayout,
) -> dict[str, Any]:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    belt_speed = _safe_load(load_belt_speed, storage.belt_speed_file)
    photo_interval = _safe_load(load_photo_interval, storage.photo_interval_file)
    frame_period = 1 / config.fps

    return {
        "timestamp": now,
        "estimated_belt_speed_mm_s": belt_speed,
        "estimated_photo_interval_s": photo_interval,
        "capture_frame_desync_s": (photo_interval % frame_period) if photo_interval else None,
        "camera_type": "Intel RealSense D405",
        "fps": config.fps,
        "exposure_ms": exposure_ms,
        "resolution": f"{intrinsics.width}x{intrinsics.height}",
        "height_mm": round(ground.height_mm, 2),
        "mm_per_pixel_h": round(ground.mm_per_pixel_h, 2),
        "mm_per_pixel_v": round(ground.mm_per_pixel_v, 2),
        "observable_plane_mm": ground.observable_plane_label,
        "chessboard_calibration": {
            "fx": calibration.fx,
            "fy": calibration.fy,
            "cx": calibration.cx,
            "cy": calibration.cy,
            "reprojection_error": calibration.reprojection_error,
            "distortion_coeffs": calibration.distortion_coeffs.tolist(),
        },
        "sdk_intrinsics": {
            "fx": intrinsics.fx,
            "fy": intrinsics.fy,
            "cx": intrinsics.ppx,
            "cy": intrinsics.ppy,
            "distortion_coeffs": list(intrinsics.coeffs),
        },
    }


def _safe_load(loader: Callable[[Path], float], path: Path) -> float | None:
    """Load a state value, returning ``None`` if it has not been written yet."""
    try:
        return loader(path)
    except (FileNotFoundError, OSError, KeyError):
        return None
