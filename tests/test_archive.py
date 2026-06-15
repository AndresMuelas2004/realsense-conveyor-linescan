"""Archiving finished reconstructions into the rolling history folder.

The contract (ported from the original ``GuardarReconstrucciones``): only image
files are copied, they are renamed to a sequential number that *continues* from
whatever already lives in the history folder, and a missing/empty source is a
no-op. Numbering accumulates across runs so the history is never overwritten.
"""

from __future__ import annotations

from linescan.archive import archive_reconstructions
from linescan.config import StorageLayout


def _make_storage(tmp_path) -> StorageLayout:
    return StorageLayout(base_dir=tmp_path, data_dir=tmp_path / "data")


def _touch(path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_returns_zero_when_source_missing(tmp_path):
    storage = _make_storage(tmp_path)
    assert archive_reconstructions(storage) == 0
    # The destination is still created so later runs can append to it.
    assert storage.history_dir.is_dir()


def test_returns_zero_when_source_empty(tmp_path):
    storage = _make_storage(tmp_path)
    storage.reconstructions_dir.mkdir(parents=True)
    assert archive_reconstructions(storage) == 0


def test_copies_only_image_files(tmp_path):
    storage = _make_storage(tmp_path)
    _touch(storage.reconstructions_dir / "IR1.png")
    _touch(storage.reconstructions_dir / "IR2.jpg")
    _touch(storage.reconstructions_dir / "notes.txt")
    _touch(storage.reconstructions_dir / "data.npz")

    archived = archive_reconstructions(storage)

    assert archived == 2
    names = sorted(p.name for p in storage.history_dir.iterdir())
    # Sequential numbering, keeping each image's own extension; non-images skipped.
    assert names == ["1.png", "2.jpg"]


def test_numbering_continues_from_existing_history(tmp_path):
    storage = _make_storage(tmp_path)
    # Two files already archived from a previous run.
    _touch(storage.history_dir / "1.png")
    _touch(storage.history_dir / "2.png")
    _touch(storage.reconstructions_dir / "IR1.png")
    _touch(storage.reconstructions_dir / "IR2.png")

    archived = archive_reconstructions(storage)

    assert archived == 2
    names = sorted(p.name for p in storage.history_dir.iterdir())
    assert names == ["1.png", "2.png", "3.png", "4.png"]


def test_uppercase_extensions_are_archived(tmp_path):
    # Suffix matching is case-insensitive (``.suffix.lower()``).
    storage = _make_storage(tmp_path)
    _touch(storage.reconstructions_dir / "IR1.PNG")
    _touch(storage.reconstructions_dir / "IR2.JPG")

    assert archive_reconstructions(storage) == 2


def test_file_contents_are_preserved(tmp_path):
    storage = _make_storage(tmp_path)
    _touch(storage.reconstructions_dir / "IR1.png", content=b"hello-bytes")

    archive_reconstructions(storage)

    copied = next(storage.history_dir.iterdir())
    assert copied.read_bytes() == b"hello-bytes"
