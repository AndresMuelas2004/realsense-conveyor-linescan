"""Reconstruction primitives: overlap removal, belt depth, and strip stitching.

``compute_overlap_pixels`` and ``belt_depth_from_samples`` are pure and unit
tested. The stitching/saving helpers do the OpenCV I/O the capture loop offloads
to worker threads.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import Future
from pathlib import Path

import cv2
import numpy as np

# Scale factor applied when flattening a 16-bit depth strip to an 8-bit preview
# image (so the stitched depth map is viewable as grayscale).
DEPTH_VISUALIZATION_ALPHA = 0.03


def compute_overlap_pixels(
    advances: Sequence[float],
    offsets: Sequence[float],
    photo_interval_s: float,
    margin_s: float,
    mm_per_pixel_v: float,
    pixels_captured: int,
) -> int:
    """Number of overlapping rows to trim from the bottom of a strip.

    Captures are intentionally taken slightly *early* (interval minus a margin)
    to force overlap rather than gaps, because a gap is unrecoverable while an
    overlap can be measured and trimmed. The overlap in time is reconstructed
    from the per-capture timing offsets, converted to millimetres via the belt
    speed, then to rows via the vertical pixel pitch. Faithful port of the
    original ``eliminarPixeles`` (see README -> How overlap removal works).
    """
    if len(offsets) == 1:
        advance_prev = 0.0
        offset_prev = 0.0
    else:
        advance_prev = advances[-2]
        offset_prev = offsets[-2]
    advance_now = advances[-1]
    offset_now = offsets[-1]

    overlap_time_s = margin_s + advance_prev - advance_now + offset_now - offset_prev
    strip_height_mm = mm_per_pixel_v * pixels_captured
    belt_speed_mm_s = strip_height_mm / photo_interval_s
    overlap_length_mm = belt_speed_mm_s * overlap_time_s
    return int(overlap_length_mm / mm_per_pixel_v)


def belt_depth_from_samples(samples: Sequence[Sequence[float]]) -> float:
    """Reference belt depth (mm) from several rows of point samples.

    The original averaged each column across the sample rows and then averaged
    those column means; that is exactly the mean of every sample, computed here
    directly.
    """
    return float(np.asarray(samples, dtype=float).mean())


def save_strip(path: Path, image: np.ndarray) -> None:
    """Write one captured strip to disk (offloaded to a worker thread)."""
    cv2.imwrite(str(path), image)


def stitch_color(
    strip_paths: Sequence[Path],
    output_path: Path,
    *,
    skip_path: Path | None = None,
    wait_for: Future | None = None,
) -> None:
    """Stack saved color strips vertically into one reconstructed image."""
    if wait_for is not None:
        wait_for.result()  # ensure the last strip is fully written before reading
    images = _read_strips(strip_paths, skip_path, cv2.IMREAD_COLOR)
    cv2.imwrite(str(output_path), np.vstack(images))


def stitch_depth(
    strip_paths: Sequence[Path],
    output_path: Path,
    *,
    skip_path: Path | None = None,
    wait_for: Future | None = None,
) -> None:
    """Stack saved depth strips vertically into one viewable grayscale image."""
    if wait_for is not None:
        wait_for.result()
    images = _read_strips(strip_paths, skip_path, cv2.IMREAD_UNCHANGED)
    stacked = np.vstack(images)
    preview = cv2.convertScaleAbs(stacked, alpha=DEPTH_VISUALIZATION_ALPHA)
    cv2.imwrite(str(output_path), preview)


def _read_strips(
    strip_paths: Sequence[Path], skip_path: Path | None, flags: int
) -> list[np.ndarray]:
    """Load strip images, skipping a known-bad path and any that fail to read.

    ``skip_path`` is the second strip of the first reconstruction: during that
    window the belt depth is still being measured and no part can be present, so
    that strip is intentionally dropped.
    """
    images: list[np.ndarray] = []
    for path in strip_paths:
        if skip_path is not None and Path(path) == Path(skip_path):
            continue
        image = cv2.imread(str(path), flags)
        if image is not None:
            images.append(image)
    return images
