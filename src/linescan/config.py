"""Static configuration: the camera/rig parameters and where files live on disk.

Nothing here touches hardware or the filesystem at import time. ``CameraConfig``
mirrors the hand-entered values of the original project, and ``StorageLayout``
centralizes every path the station reads from or writes to (so folder names are
defined once instead of being scattered as string literals across the code).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Root of the installed/checked-out project (…/src/linescan/config.py -> project root).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


@dataclass(frozen=True)
class CameraConfig:
    """Camera and rig parameters the operator sets once for a given station.

    Defaults reproduce the original deployment (an Intel RealSense D405 used at
    1280x720). ``fov_*`` are informational only — they are kept because they
    describe the camera but are not used by any calculation.
    """

    fov_horizontal_deg: float = 87.0
    fov_vertical_deg: float = 58.0
    width_px: int = 1280
    height_px: int = 720

    # Physical size of a single sensor pixel. The D405 datasheet does not publish
    # the sensor/pixel dimensions, so this is an estimate; it cancels out of the
    # mm-per-pixel result (focal length in mm is derived from it and then divided
    # back out), which is why the reconstruction stays accurate despite it.
    pixel_size_mm: float = 0.003

    fps: int = 30
    # Manual exposure used during capture, in microseconds (RealSense units).
    exposure_us: int = 2000

    # Diameter of the encoder roller the magnet rides on. A larger roller raises
    # the maximum measurable belt speed (see README -> Limitations).
    roller_encoder_diameter_mm: float = 63.6

    # Number of central vertical pixels kept from each frame to build the strip.
    # Must stay above ~80-100: the overlap-removal step always trims tens of
    # pixels regardless of strip size, so a thin strip would vanish.
    captured_vertical_pixels: int = 100

    @property
    def sensor_width_mm(self) -> float:
        return self.width_px * self.pixel_size_mm

    @property
    def sensor_height_mm(self) -> float:
        return self.height_px * self.pixel_size_mm


@dataclass(frozen=True)
class StorageLayout:
    """All paths the station reads from or writes to, resolved from a base dir.

    The original project hard-coded Spanish folder names (``ImagenesReconstruidas``,
    ``Imagenes guardadas``, ``HISTORIAL RECONSTRUCCIONES``). They are renamed here
    to ``reconstructions`` / ``strips`` / ``history`` (see README -> Migration).
    Runtime output defaults to the current working directory so an operator can
    run the tool from wherever the captures should land; the committed example
    calibration and height live under ``data/`` by default.
    """

    base_dir: Path = field(default_factory=Path.cwd)
    data_dir: Path = DEFAULT_DATA_DIR

    # --- Output produced at runtime (git-ignored) ---
    @property
    def reconstructions_dir(self) -> Path:
        return self.base_dir / "reconstructions"

    @property
    def strips_dir(self) -> Path:
        return self.base_dir / "strips"

    @property
    def history_dir(self) -> Path:
        return self.base_dir / "history"

    @property
    def parameter_log_file(self) -> Path:
        return self.base_dir / "camera_parameters_log.json"

    # --- Persisted calibration / measured state ---
    @property
    def calibration_file(self) -> Path:
        return self.data_dir / "calibration" / "chessboard_calibration.npz"

    @property
    def height_file(self) -> Path:
        return self.data_dir / "state" / "height_mm.npy"

    @property
    def belt_speed_file(self) -> Path:
        return self.data_dir / "state" / "belt_speed.npz"

    @property
    def photo_interval_file(self) -> Path:
        return self.data_dir / "state" / "photo_interval.npz"

    def strip_dir_for(self, reconstruction_index: int) -> Path:
        """Folder holding the per-strip images of one reconstruction (``strips/IR<n>``)."""
        return self.strips_dir / f"IR{reconstruction_index}"
