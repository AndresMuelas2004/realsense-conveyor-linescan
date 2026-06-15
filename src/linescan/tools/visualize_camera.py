"""Live color preview, so the operator can see what the camera captures.

Port of ``VISUALIZACION_CAMARA``. Use it to align the camera so the belt edges
run parallel to the window borders — the camera's vertical axis must be parallel
to the belt's travel direction for the reconstruction to be correct.
"""

from __future__ import annotations

from ..camera import RealSenseCamera
from ..config import CameraConfig
from ..keys import quit_pressed


def visualize_camera(config: CameraConfig) -> None:
    """Open the color stream with auto-exposure and show it until 'q'."""
    import cv2

    with RealSenseCamera(config) as camera:
        camera.start(color=True, auto_exposure=True)
        try:
            while not quit_pressed():
                frames = camera.poll_frames()
                if not frames:
                    continue
                color = camera.color_frame(frames)
                if color is None:
                    continue
                cv2.imshow("Camera", camera.to_image(color))
                cv2.waitKey(1)
        finally:
            cv2.destroyAllWindows()
