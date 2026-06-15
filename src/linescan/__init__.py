"""Line-scan reconstruction and measurement for objects on a conveyor belt.

This package turns an Intel RealSense depth camera into a synchronized
line-scan scanner: it grabs a thin central strip from every frame, removes the
overlap caused by capture-timing jitter, and stacks the strips into a single
reconstructed image of each part as it travels under the camera. Belt speed is
measured by a Hall-effect sensor reading a magnet on the encoder roller.

See the README for the full operator workflow and the physics behind it.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
