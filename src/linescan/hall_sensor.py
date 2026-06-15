"""Belt-speed sensing from a Hall-effect sensor on the encoder roller.

A microcontroller (e.g. an ESP32) watches a magnet pass a Hall sensor on the
roller and emits two markers over serial: ``bb`` when the magnet is approaching
and ``hh`` on detection. The time between consecutive detections is one belt
revolution; from the roller circumference we get belt speed, and from belt speed
and the strip height we get the interval between captures the camera must use.

The sensor runs on its own background thread and publishes a thread-safe list of
computed photo intervals that the capture loop consumes.
"""

from __future__ import annotations

import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .config import CameraConfig, StorageLayout
from .keys import quit_pressed
from .state import save_belt_speed, save_photo_interval

# Serial markers emitted by the microcontroller.
MARKER_APPROACHING = "bb"
MARKER_DETECTED = "hh"

# A revolution longer than this multiple of the previous one is treated as a
# missed/garbled pulse and discarded.
OUTLIER_FACTOR = 1.7
# Revolutions averaged to estimate the current speed (rolling window).
REVOLUTIONS_AVERAGED = 5
# Revolutions required before the first interval is published (lets the rolling
# average settle and lets the operator vary the belt speed beforehand).
MIN_REVOLUTIONS = 7


class BeltSpeedSensor:
    """Background reader that turns Hall pulses into capture intervals.

    Parameters
    ----------
    mm_per_pixel_v:
        Vertical millimetres per pixel at the working height; needed to convert
        belt speed into the time between captures.
    """

    def __init__(
        self,
        config: CameraConfig,
        storage: StorageLayout,
        mm_per_pixel_v: float,
        *,
        port: str = "COM3",
        baudrate: int = 115200,
    ) -> None:
        self._config = config
        self._storage = storage
        self._mm_per_pixel_v = mm_per_pixel_v
        self._port = port
        self._baudrate = baudrate

        self._photo_intervals: list[float] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._disk_writer = ThreadPoolExecutor(max_workers=2)

    # --- public, thread-safe view of the readings -------------------------
    @property
    def interval_count(self) -> int:
        with self._lock:
            return len(self._photo_intervals)

    @property
    def latest_interval(self) -> float | None:
        """Most recent capture interval (seconds), or ``None`` if not ready yet."""
        with self._lock:
            return self._photo_intervals[-1] if self._photo_intervals else None

    # --- lifecycle --------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("BeltSpeedSensor already started.")
        self._thread = threading.Thread(target=self._run, name="hall-sensor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._disk_writer.shutdown(wait=False)

    # --- worker -----------------------------------------------------------
    def _run(self) -> None:
        import serial  # lazy: only the rig needs the serial link

        magnet_detected = False
        revolution_times: list[float] = []
        start = time.perf_counter()

        connection = serial.Serial(self._port, self._baudrate, timeout=1)
        print("Listening to the Hall sensor...")
        print("Computing belt speed and capture interval...")
        try:
            while not self._stop.is_set() and not quit_pressed():
                elapsed = time.perf_counter() - start
                if not connection.in_waiting:
                    continue
                line = connection.readline().decode().strip()
                if line == MARKER_DETECTED:
                    if magnet_detected:
                        start = self._on_revolution(revolution_times, elapsed)
                    magnet_detected = False
                elif line == MARKER_APPROACHING:
                    magnet_detected = True
        finally:
            connection.close()

    def _on_revolution(self, revolution_times: list[float], elapsed: float) -> float:
        """Record one revolution; publish a new interval once enough are seen.

        Returns the new ``perf_counter`` baseline for the next revolution.
        """
        revolution_times.append(elapsed)
        # Compare against the previous *kept* revolution to reject garbled pulses.
        # Indexing with ``len - 2`` (not Python's ``-2``) is deliberate: on the
        # very first sample it resolves to the sample itself, making the check a
        # harmless no-op instead of an IndexError — exactly as the original did.
        previous = revolution_times[len(revolution_times) - 2]
        if elapsed > previous * OUTLIER_FACTOR:
            print("Hall sensor measurement error")
            revolution_times.pop()
        else:
            print(f"Revolution time: {elapsed}")

        baseline = time.perf_counter()

        if len(revolution_times) >= MIN_REVOLUTIONS:
            interval = self._photo_interval_from(revolution_times)
            self._disk_writer.submit(save_photo_interval, self._storage.photo_interval_file, interval)
            with self._lock:
                self._photo_intervals.append(interval)
        return baseline

    def _photo_interval_from(self, revolution_times: list[float]) -> float:
        """Compute the capture interval from the last few revolutions."""
        window = revolution_times[-REVOLUTIONS_AVERAGED:]
        mean_revolution_s = sum(window) / REVOLUTIONS_AVERAGED

        circumference_mm = math.pi * self._config.roller_encoder_diameter_mm
        belt_speed_mm_s = circumference_mm / mean_revolution_s
        print(f"Belt speed: {belt_speed_mm_s} mm/s")
        self._disk_writer.submit(save_belt_speed, self._storage.belt_speed_file, belt_speed_mm_s)

        strip_height_mm = self._mm_per_pixel_v * self._config.captured_vertical_pixels
        return strip_height_mm / belt_speed_mm_s
