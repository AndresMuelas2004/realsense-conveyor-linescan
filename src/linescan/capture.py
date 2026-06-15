"""The capture pipeline: turn the moving belt into one image per part.

This is the heart of the system and a faithful port of the original
``CAPTURAR_IMAGENES`` script. The control flow and every numeric threshold are
preserved; the ~25 module-level globals of the original are now named attributes
of :class:`PieceCaptureSession`, and the disk/stitch work still runs on worker
threads so the hot loop keeps up with the camera.

High-level loop, once per frame:

1. Read the latest capture interval from the Hall sensor.
2. Grab the newest color+depth frames (non-blocking).
3. If a part just finished, stitch its strips into a reconstruction.
4. Every ``interval - margin`` seconds, cut a central strip, trim the overlap,
   measure the belt depth (once), detect whether a part is under the camera, and
   save strips while one is.

On exit it cleans up partial output, logs the run parameters and archives the
reconstructions.
"""

from __future__ import annotations

import math
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from . import archive, report
from .calibration import CameraCalibration
from .camera import RealSenseCamera
from .config import CameraConfig, StorageLayout
from .geometry import GroundSampling
from .hall_sensor import BeltSpeedSensor
from .keys import quit_pressed
from .reconstruction import (
    belt_depth_from_samples,
    compute_overlap_pixels,
    save_strip,
    stitch_color,
    stitch_depth,
)

# Columns sampled across the belt to establish its reference depth.
DEPTH_SAMPLE_COLUMNS = (160, 320, 480, 640, 840, 960, 1140)
# Columns scanned on each strip row to decide whether a part is present.
PIECE_SCAN_COLUMNS = range(100, 1100, 10)
# Depth captures to skip before trusting the belt-depth samples.
DEPTH_WARMUP_CAPTURES = 2
# Belt-depth sample rows to average before locking in the reference depth.
BELT_DEPTH_SAMPLE_COUNT = 5
# A point rising more than this above the belt counts as "part" — with an upper
# bound (half the belt depth) to reject the spurious 0-depth readings the camera
# occasionally returns.
PIECE_DEPTH_DELTA_MIN_MM = 70
# Brief yield so the Hall sensor thread reads its pulses cleanly (empirically
# necessary in the original; cause unknown but kept).
POLL_SLEEP_S = 0.00001


class PieceCaptureSession:
    """Owns one run of the capture loop and all of its mutable state."""

    def __init__(
        self,
        config: CameraConfig,
        calibration: CameraCalibration,
        ground_sampling: GroundSampling,
        storage: StorageLayout,
        *,
        serial_port: str = "COM3",
        sensor: BeltSpeedSensor | None = None,
    ) -> None:
        self._config = config
        self._calibration = calibration
        self._ground = ground_sampling
        self._storage = storage
        self._sensor = sensor or BeltSpeedSensor(
            config, storage, ground_sampling.mm_per_pixel_v, port=serial_port
        )
        self._executor = ThreadPoolExecutor(max_workers=5)

        # Central-strip bounds within the full frame (height axis).
        half_h = int(config.height_px / 2)
        self._strip_top = half_h - int(config.captured_vertical_pixels / 2)
        self._strip_bottom = half_h + math.ceil(config.captured_vertical_pixels / 2)
        self._margin_s = 1 / config.fps

        # --- mutable run state ---
        self._t0 = time.perf_counter()
        self._reconstruction_index = 0
        self._has_joined = False
        self._color_strip_paths: list[Path] = []
        self._depth_strip_paths: list[Path] = []
        self._advances: list[float] = []
        self._offsets_color: list[float] = []
        self._offsets_depth: list[float] = []
        self._belt_depth_samples: list[list[int]] = []
        self._depth_capture_count = 0
        self._belt_depth_measured = False
        self._belt_depth = 0.0
        self._piece_detected = False
        self._previous_piece_detected: bool | None = None
        self._join_pending = False
        self._save_strips = False
        self._saved_previous = False
        self._can_place_pieces = False

        # Latest frame data, refreshed every iteration.
        self._color_image = np.zeros((config.height_px, config.width_px, 3), dtype=np.uint8)
        self._depth_image: np.ndarray | None = None
        self._valid_color_frame: Any = None  # RealSense frame (untyped C binding)
        self._valid_depth_frame: Any = None
        self._offset = 0.0
        self._previous_color_strip: np.ndarray | None = None

        # Futures for the most recent disk save / stitch jobs.
        self._last_color_save: Future | None = None
        self._last_depth_save: Future | None = None
        self._stitch_color_future: Future | None = None
        self._stitch_depth_future: Future | None = None

    # --- public entry point ----------------------------------------------
    def run(self) -> None:
        """Run the capture loop until the operator presses 'q'."""
        self._prepare()
        self._sensor.start()
        try:
            with RealSenseCamera(self._config) as camera:
                camera.start(
                    color=True,
                    depth=True,
                    auto_exposure=False,
                    exposure_us=self._config.exposure_us,
                )
                self._loop(camera)
        finally:
            self._sensor.stop()
            self._executor.shutdown(wait=True)
            self._cleanup_partial_output()
            self._log_and_archive()

    # --- setup ------------------------------------------------------------
    def _prepare(self) -> None:
        for directory in (
            self._storage.reconstructions_dir,
            self._storage.strips_dir,
            self._storage.history_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self._announce_camera()
        _clear_directory(self._storage.reconstructions_dir)
        _clear_directory(self._storage.strips_dir)
        print(
            "Showing the camera view.\n"
            " -- The reconstructions are saved to 'reconstructions/'.\n"
            " -- Press 'q' to stop."
        )

    def _announce_camera(self) -> None:
        names = RealSenseCamera(self._config).list_device_names()
        if not names:
            print("--- NO DEVICE CONNECTED ---")
        else:
            print("Device found:", names[0])

    # --- main loop --------------------------------------------------------
    def _loop(self, camera: RealSenseCamera) -> None:
        import cv2

        if not self._wait_for_first_interval():
            return

        while not quit_pressed():
            time.sleep(POLL_SLEEP_S)
            interval = self._sensor.latest_interval
            if interval is None:
                continue

            self._grab_latest_frames(camera, cv2)

            if self._join_pending:
                self._join_reconstruction()

            elapsed = time.perf_counter() - self._t0
            if elapsed >= (interval - self._margin_s):
                self._process_capture(elapsed, interval)

            if not self._can_place_pieces and self._belt_depth_measured:
                print(" ___ Parts may now pass ___ ")
                self._can_place_pieces = True

    def _wait_for_first_interval(self) -> bool:
        """Block until the Hall sensor produces its first interval (or 'q')."""
        while self._sensor.interval_count == 0:
            time.sleep(POLL_SLEEP_S)
            if quit_pressed():
                return False
        return True

    def _grab_latest_frames(self, camera: RealSenseCamera, cv2) -> None:
        frames = camera.poll_frames()
        if not frames:
            return
        color = camera.color_frame(frames)
        depth = camera.depth_frame(frames)
        if color is not None:
            self._color_image = camera.to_image(color)
            self._valid_color_frame = color
            self._offset = time.perf_counter() - color.get_timestamp() / 1000
            strip = self._color_image[self._strip_top : self._strip_bottom, :]
            cv2.imshow("Camera", strip)
            cv2.pollKey() if hasattr(cv2, "pollKey") else cv2.waitKey(1)
        if depth is not None:
            self._depth_image = camera.to_image(depth)
            self._valid_depth_frame = depth

    def _join_reconstruction(self) -> None:
        """Stitch the strips of the part that just finished into one image."""
        self._reconstruction_index += 1
        index = self._reconstruction_index
        color_paths = list(self._color_strip_paths)
        depth_paths = list(self._depth_strip_paths)

        self._stitch_color_future = self._executor.submit(
            stitch_color,
            color_paths,
            self._storage.reconstructions_dir / f"IR{index}.png",
            skip_path=self._storage.strip_dir_for(1) / "color_2.png",
            wait_for=self._last_color_save,
        )
        self._stitch_depth_future = self._executor.submit(
            stitch_depth,
            depth_paths,
            self._storage.reconstructions_dir / f"IRP{index}.png",
            skip_path=self._storage.strip_dir_for(1) / "depth_2.png",
            wait_for=self._last_depth_save,
        )
        self._color_strip_paths.clear()
        self._depth_strip_paths.clear()
        self._storage.strip_dir_for(index + 1).mkdir(parents=True, exist_ok=True)
        self._has_joined = True
        self._join_pending = False
        print(f"Reconstruction number: {index}")

    def _process_capture(self, elapsed: float, interval: float) -> None:
        """Cut and trim one strip, update detection, and persist while a part runs."""
        color_frame = self._valid_color_frame
        depth_frame = self._valid_depth_frame
        depth_image = self._depth_image
        if color_frame is None or depth_frame is None or depth_image is None:
            return  # no frame has arrived yet; wait for the next iteration
        if self._reconstruction_index == 0:
            self._storage.strip_dir_for(1).mkdir(parents=True, exist_ok=True)

        self._depth_capture_count += 1
        advance = elapsed - (interval - self._margin_s)
        self._t0 = time.perf_counter()
        self._advances.append(advance)

        overlap_color = self._record_overlap(self._offsets_color, color_frame, interval)
        overlap_depth = self._record_overlap(self._offsets_depth, depth_frame, interval)

        depth_strip = depth_image[self._strip_top : self._strip_bottom - overlap_depth, :]
        color_strip = self._color_image[self._strip_top : self._strip_bottom - overlap_color, :]

        self._maybe_measure_belt_depth(depth_image, overlap_depth)
        if self._belt_depth_measured:
            self._update_piece_detection(depth_strip)
        if self._save_strips:
            self._persist_strips(color_strip, depth_strip)

        self._previous_color_strip = color_strip

    def _record_overlap(self, offsets: list[float], frame: Any, interval: float) -> int:
        """Append this capture's timing offset and return the rows to trim."""
        offset = time.perf_counter() - (frame.get_timestamp() / 1000 + self._offset)
        offsets.append(offset)
        return compute_overlap_pixels(
            self._advances,
            offsets,
            interval,
            self._margin_s,
            self._ground.mm_per_pixel_v,
            self._config.captured_vertical_pixels,
        )

    def _maybe_measure_belt_depth(self, depth_image: np.ndarray, overlap_depth: int) -> None:
        """Lock in the reference belt depth from a few early samples."""
        if self._depth_capture_count <= DEPTH_WARMUP_CAPTURES or self._belt_depth_measured:
            return
        row = self._strip_bottom - overlap_depth
        samples = [int(depth_image[row, col]) for col in DEPTH_SAMPLE_COLUMNS]
        self._belt_depth_samples.append(samples)
        if len(self._belt_depth_samples) == BELT_DEPTH_SAMPLE_COUNT:
            self._belt_depth = belt_depth_from_samples(self._belt_depth_samples)
            self._belt_depth_measured = True

    def _update_piece_detection(self, depth_strip: np.ndarray) -> None:
        """Detect part presence and flag start/end transitions.

        A part is present when the *last* strip row shows a point rising between
        ``PIECE_DEPTH_DELTA_MIN_MM`` and half the belt depth above the belt. This
        last-row behavior matches the original exactly.
        """
        rows = [
            [int(depth_strip[v, h]) for h in PIECE_SCAN_COLUMNS]
            for v in range(0, depth_strip.shape[0])
        ]
        if not rows:
            return

        belt_row = np.full(len(rows[0]), self._belt_depth)
        detected = self._piece_detected
        for row in rows:
            deltas = np.abs(np.array(row) - belt_row)
            for delta in deltas:
                if delta > PIECE_DEPTH_DELTA_MIN_MM and delta < (self._belt_depth / 2):
                    detected = True
                    break
                detected = False
        self._piece_detected = detected

        if self._previous_piece_detected is not None:
            if self._previous_piece_detected and not detected:
                # Part just left the field of view -> stitch its strips.
                self._join_pending = True
                self._save_strips = False
            elif not self._previous_piece_detected and detected:
                # Part just entered -> start saving strips.
                self._save_strips = True
                self._saved_previous = False
        self._previous_piece_detected = detected

    def _persist_strips(self, color_strip: np.ndarray, depth_strip: np.ndarray) -> None:
        """Save the current strips (and, once, the one just before the part)."""
        strip_dir = self._storage.strip_dir_for(self._reconstruction_index + 1)
        if not self._saved_previous:
            # Include the frame captured just before detection (color uses the
            # previous strip; depth reuses the current one, as in the original).
            if self._previous_color_strip is not None:
                self._last_color_save = self._submit_strip(
                    strip_dir, "color", self._previous_color_strip
                )
                self._last_depth_save = self._submit_strip(strip_dir, "depth", depth_strip)
            self._saved_previous = True
        self._last_color_save = self._submit_strip(strip_dir, "color", color_strip)
        self._last_depth_save = self._submit_strip(strip_dir, "depth", depth_strip)

    def _submit_strip(self, strip_dir: Path, kind: str, image: np.ndarray) -> Future:
        paths = self._color_strip_paths if kind == "color" else self._depth_strip_paths
        path = strip_dir / f"{kind}_{len(paths) + 1}.png"
        paths.insert(0, path)
        return self._executor.submit(save_strip, paths[0], image)

    # --- teardown ---------------------------------------------------------
    def _cleanup_partial_output(self) -> None:
        first = self._storage.reconstructions_dir / "IR1.png"
        if first.exists() and self._reconstruction_index == 0:
            first.unlink()
        for future in (self._stitch_color_future, self._stitch_depth_future):
            if self._has_joined and future is not None:
                future.result()
        pending_strip_dir = self._storage.strip_dir_for(self._reconstruction_index + 1)
        if pending_strip_dir.is_dir():
            _remove_tree(pending_strip_dir)

    def _log_and_archive(self) -> None:
        try:
            report.write_parameter_log(
                self._config, self._calibration, self._ground, self._storage
            )
        except Exception as exc:  # pragma: no cover - depends on the rig
            print(f"Could not write the parameter log: {exc}")
        try:
            archive.archive_reconstructions(self._storage)
        except Exception as exc:  # pragma: no cover - depends on runtime output
            print(f"Could not archive the reconstructions: {exc}")


def _clear_directory(directory: Path) -> None:
    """Delete every file/sub-folder inside ``directory`` (keep the folder)."""
    if not directory.is_dir():
        return
    for entry in directory.iterdir():
        _remove_tree(entry)


def _remove_tree(path: Path) -> None:
    import shutil

    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
