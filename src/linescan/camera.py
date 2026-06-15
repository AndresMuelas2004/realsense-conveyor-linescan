"""Thin wrapper around the Intel RealSense pipeline.

Centralizes every camera operation the original scripts each re-implemented:
opening color/depth streams, fixing or auto-ing exposure, polling vs. waiting
for frames, turning frames into NumPy arrays, reading a depth distance and
reading the live intrinsics.

``pyrealsense2`` is imported lazily inside the methods, so importing this module
(and the whole package) never requires the RealSense SDK to be installed — only
actually opening a camera does.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .config import CameraConfig


class RealSenseError(RuntimeError):
    """Raised when the camera is missing or misconfigured."""


def _import_rs() -> Any:
    try:
        import pyrealsense2 as rs
    except ImportError as exc:  # pragma: no cover - exercised only off-rig
        raise RealSenseError(
            "pyrealsense2 is not installed. Install the Intel RealSense SDK 2.0 "
            "Python bindings (`pip install pyrealsense2`) to use the camera."
        ) from exc
    return rs


class RealSenseCamera:
    """Manages a single RealSense streaming session.

    Use it as a context manager so the pipeline is always stopped::

        with RealSenseCamera(config) as cam:
            cam.start(color=True, depth=True, exposure_us=2000)
            frames = cam.wait_frames()
            image = cam.to_image(cam.color_frame(frames))
    """

    def __init__(self, config: CameraConfig) -> None:
        self._config = config
        self._rs = _import_rs()
        self._pipeline: Any | None = None
        self._profile: Any | None = None

    # --- device discovery -------------------------------------------------
    def list_device_names(self) -> list[str]:
        rs = self._rs
        ctx = rs.context()
        return [d.get_info(rs.camera_info.name) for d in ctx.query_devices()]

    def is_connected(self) -> bool:
        return len(self.list_device_names()) > 0

    # --- lifecycle --------------------------------------------------------
    def start(
        self,
        *,
        color: bool = True,
        depth: bool = False,
        auto_exposure: bool | None = None,
        exposure_us: int | None = None,
    ) -> None:
        """Open the requested streams and (optionally) configure exposure."""
        rs = self._rs
        cfg = self._config
        pipeline = rs.pipeline()
        rs_config = rs.config()
        if color:
            rs_config.enable_stream(
                rs.stream.color, cfg.width_px, cfg.height_px, rs.format.bgr8, cfg.fps
            )
        if depth:
            rs_config.enable_stream(
                rs.stream.depth, cfg.width_px, cfg.height_px, rs.format.z16, cfg.fps
            )
        self._profile = pipeline.start(rs_config)
        self._pipeline = pipeline

        if auto_exposure is not None or exposure_us is not None:
            self._configure_exposure(auto_exposure=auto_exposure, exposure_us=exposure_us)

    def _configure_exposure(
        self, *, auto_exposure: bool | None, exposure_us: int | None
    ) -> None:
        rs = self._rs
        sensor = self._exposure_sensor()
        if sensor is None:
            raise RealSenseError("No sensor with exposure control was found.")
        if auto_exposure is not None:
            sensor.set_option(rs.option.enable_auto_exposure, bool(auto_exposure))
        if exposure_us is not None:
            sensor.set_option(rs.option.exposure, float(exposure_us))

    def _exposure_sensor(self) -> Any | None:
        rs = self._rs
        device = self._require_profile().get_device()
        for sensor in device.query_sensors():
            if sensor.supports(rs.option.exposure):
                return sensor
        return None

    def stop(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()
            self._pipeline = None
            self._profile = None

    def __enter__(self) -> RealSenseCamera:
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # --- frame access -----------------------------------------------------
    def _require_pipeline(self) -> Any:
        if self._pipeline is None:
            raise RealSenseError("Camera pipeline is not running; call start() first.")
        return self._pipeline

    def _require_profile(self) -> Any:
        if self._profile is None:
            raise RealSenseError("Camera pipeline is not running; call start() first.")
        return self._profile

    def wait_frames(self) -> Any:
        """Block until a coherent frameset is available."""
        return self._require_pipeline().wait_for_frames()

    def poll_frames(self) -> Any | None:
        """Return the latest frameset if one is ready, else ``None`` (non-blocking)."""
        frames = self._require_pipeline().poll_for_frames()
        return frames if frames else None

    def warmup(self, frames: int) -> None:
        """Discard the first few framesets while auto-exposure/depth stabilize."""
        for _ in range(frames):
            self.wait_frames()

    @staticmethod
    def color_frame(frames: Any) -> Any | None:
        frame = frames.get_color_frame()
        return frame if frame else None

    @staticmethod
    def depth_frame(frames: Any) -> Any | None:
        frame = frames.get_depth_frame()
        return frame if frame else None

    @staticmethod
    def to_image(frame: Any) -> np.ndarray:
        """Convert a RealSense frame into a NumPy array view of its pixels."""
        return np.asanyarray(frame.get_data())

    @staticmethod
    def distance_mm(depth_frame: Any, x: float, y: float) -> float:
        """Depth at pixel ``(x, y)`` in millimetres (0 where depth is invalid)."""
        return depth_frame.get_distance(int(x), int(y)) * 1000

    # --- live intrinsics / options ---------------------------------------
    def color_intrinsics(self) -> Any:
        """Intrinsics reported by the SDK for the active color stream."""
        rs = self._rs
        video_stream = self._require_profile().get_stream(rs.stream.color).as_video_stream_profile()
        return video_stream.get_intrinsics()

    def exposure_raw(self) -> float:
        """Current exposure as reported by the depth sensor (RealSense units)."""
        rs = self._rs
        sensor = self._require_profile().get_device().first_depth_sensor()
        return sensor.get_option(rs.option.exposure)
