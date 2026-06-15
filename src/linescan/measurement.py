"""Interactive tool to measure real distances on a reconstructed image.

Port of ``MEDIR_PIEZA_RECONSTRUIDA``. Open a reconstruction, zoom with the
mouse wheel, pan by dragging the right button, and left-click two points to
print the real-world distance between them (using the per-axis mm-per-pixel of
the working height). Accuracy depends on the reconstruction quality — see the
README -> Limitations.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .config import StorageLayout
from .geometry import GroundSampling, pixel_distance_mm

WINDOW_NAME = "Select two points"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
ZOOM_MIN = 0.2
ZOOM_MAX = 10.0
ZOOM_STEP = 0.1
POINT_RADIUS = 1


@dataclass
class _ViewState:
    zoom: float = 1.0
    # offset is [vertical, horizontal] in zoomed-image pixels.
    offset: np.ndarray = None  # type: ignore[assignment]
    drag_start: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        if self.offset is None:
            self.offset = np.array([0, 0], dtype=np.int32)


class ReconstructionMeasurer:
    """Owns the viewer window, its zoom/pan state and the point-pair logic."""

    def __init__(self, image: np.ndarray, ground: GroundSampling) -> None:
        self._image = image
        self._ground = ground
        self._view = _ViewState()
        self._points: list[tuple[int, int]] = []  # (column, row) in full-res pixels
        self._pair_count = 1  # toggles point color every two points

    def run(self) -> None:
        print(
            " - Zoom in/out with the mouse wheel\n"
            " - Right-click and drag to pan\n"
            " - Left-click two points to measure the distance between them"
        )
        cv2.namedWindow(WINDOW_NAME)
        cv2.setMouseCallback(WINDOW_NAME, self._on_mouse)
        while True:
            view = self._render_view((WINDOW_WIDTH, WINDOW_HEIGHT))
            cv2.imshow(WINDOW_NAME, view)
            if cv2.waitKey(1) != -1:  # any key closes the window
                break
        cv2.destroyAllWindows()

    def _render_view(self, win_size: tuple[int, int]) -> np.ndarray:
        """Resize by the current zoom and crop the panned window region."""
        zoomed = cv2.resize(
            self._image, None, fx=self._view.zoom, fy=self._view.zoom, interpolation=cv2.INTER_LINEAR
        )
        zoomed_h, zoomed_w = zoomed.shape[:2]
        win_w, win_h = win_size

        offset = self._view.offset
        offset[0] = np.clip(offset[0], 0, max(zoomed_h - win_h, 0))
        offset[1] = np.clip(offset[1], 0, max(zoomed_w - win_w, 0))
        y1, y2 = offset[0], offset[0] + win_h
        x1, x2 = offset[1], offset[1] + win_w

        view = np.zeros((win_h, win_w, 3), dtype=np.uint8)
        crop = zoomed[y1:y2, x1:x2]
        view[0 : crop.shape[0], 0 : crop.shape[1]] = crop
        return view

    def _on_mouse(self, event: int, x: int, y: int, flags: int, _param: object) -> None:
        if event == cv2.EVENT_MOUSEWHEEL:
            self._zoom_at(x, y, zoom_in=flags > 0)
        elif event == cv2.EVENT_RBUTTONDOWN:
            self._view.drag_start = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and flags & cv2.EVENT_FLAG_RBUTTON:
            self._pan(x, y)
        elif event == cv2.EVENT_LBUTTONDOWN:
            self._add_point(x, y)

    def _zoom_at(self, x: int, y: int, *, zoom_in: bool) -> None:
        factor = 1 + ZOOM_STEP if zoom_in else 1 - ZOOM_STEP
        new_zoom = float(np.clip(self._view.zoom * factor, ZOOM_MIN, ZOOM_MAX))
        if new_zoom == self._view.zoom:
            return
        offset = self._view.offset
        # Keep the pixel under the cursor anchored while zooming.
        rel_x = (x + offset[1]) / self._view.zoom
        rel_y = (y + offset[0]) / self._view.zoom
        self._view.zoom = new_zoom
        offset[1] = int(rel_x * new_zoom - x)
        offset[0] = int(rel_y * new_zoom - y)

    def _pan(self, x: int, y: int) -> None:
        if self._view.drag_start is None:
            return
        dx = self._view.drag_start[0] - x
        dy = self._view.drag_start[1] - y
        self._view.offset[1] += dx
        self._view.offset[0] += dy
        self._view.drag_start = (x, y)

    def _add_point(self, x: int, y: int) -> None:
        column = int((x + self._view.offset[1]) / self._view.zoom)
        row = int((y + self._view.offset[0]) / self._view.zoom)
        self._points.append((column, row))

        color = (0, 255, 0) if self._pair_count % 2 == 0 else (0, 0, 255)
        cv2.circle(self._image, (column, row), POINT_RADIUS, color, -1)

        if len(self._points) == 2:
            self._report_distance()
            self._points.clear()
            self._pair_count += 1

    def _report_distance(self) -> None:
        (col1, row1), (col2, row2) = self._points
        distance_mm = pixel_distance_mm(
            col2, col1, row2, row1, self._ground.mm_per_pixel_h, self._ground.mm_per_pixel_v
        )
        print(f"Selected points:\n ({col1},{row1}) and ({col2},{row2})")
        print(f"Pixel distance: {abs(col2 - col1)} horizontal, {abs(row2 - row1)} vertical")
        print(f"Real distance: {distance_mm / 10} cm")
        print("_______________________________________________")


def measure_reconstruction(name: str, ground: GroundSampling, storage: StorageLayout) -> None:
    """Load reconstruction ``<name>.png`` and open the measurement viewer."""
    image_path = storage.reconstructions_dir / f"{name}.png"
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Reconstruction not found: {image_path}")
    ReconstructionMeasurer(image, ground).run()
