"""Archive finished reconstructions into a running history folder.

Port of the original ``GuardarReconstrucciones``: every image in the
``reconstructions`` folder is copied into ``history`` under a sequential number
that continues from whatever is already there, so the history accumulates across
runs.
"""

from __future__ import annotations

import shutil

from .config import StorageLayout

_IMAGE_SUFFIXES = (".png", ".jpg")


def archive_reconstructions(storage: StorageLayout) -> int:
    """Copy the current reconstructions into the history folder.

    Returns the number of images archived.
    """
    source = storage.reconstructions_dir
    destination = storage.history_dir
    destination.mkdir(parents=True, exist_ok=True)
    if not source.is_dir():
        return 0

    next_index = sum(1 for _ in destination.iterdir()) + 1
    archived = 0
    for image in sorted(source.iterdir()):
        if image.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        shutil.copy2(image, destination / f"{next_index}{image.suffix}")
        next_index += 1
        archived += 1
    return archived
