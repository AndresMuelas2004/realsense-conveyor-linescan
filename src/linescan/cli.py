"""Command-line interface tying the whole workflow together.

Each subcommand maps to one step of the operator workflow::

    linescan calibrate        # 1. chessboard intrinsic calibration (per camera)
    linescan visualize        # 2. align the camera with the belt
    linescan position         # 3. level the camera over the belt
    linescan measure-height   # 4. measure and store the camera height
    linescan show-results     # 5. review the computed parameters
    linescan capture          # 6. reconstruct parts as they pass
    linescan measure-piece IR1  # 7. measure distances on a reconstruction

Run ``linescan <command> --help`` for the options of each step.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .calibration import CameraCalibration, load_calibration, run_chessboard_calibration
from .config import DEFAULT_DATA_DIR, CameraConfig, StorageLayout
from .geometry import GroundSampling, compute_ground_sampling, compute_optical_parameters
from .state import load_height_mm


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    config = CameraConfig()
    storage = StorageLayout(base_dir=Path(args.base_dir), data_dir=Path(args.data_dir))
    try:
        args.func(args, config, storage)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="linescan", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--base-dir",
        default=str(Path.cwd()),
        help="Directory for runtime output (reconstructions/, strips/, history/). Default: cwd.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Directory holding the calibration and measured state. Default: bundled data/.",
    )

    subparsers = parser.add_subparsers(dest="command")

    p_cal = subparsers.add_parser("calibrate", help="Run the chessboard intrinsic calibration.")
    p_cal.add_argument("--image-dir", default=None, help="Where to save captured views.")
    p_cal.set_defaults(func=_cmd_calibrate)

    p_vis = subparsers.add_parser("visualize", help="Show a live color preview.")
    p_vis.set_defaults(func=_cmd_visualize)

    p_pos = subparsers.add_parser("position", help="Print symmetric depth readings for leveling.")
    p_pos.set_defaults(func=_cmd_position)

    p_height = subparsers.add_parser("measure-height", help="Measure and store the camera height.")
    p_height.set_defaults(func=_cmd_measure_height)

    p_show = subparsers.add_parser("show-results", help="Print the computed parameters.")
    p_show.set_defaults(func=_cmd_show_results)

    p_cap = subparsers.add_parser("capture", help="Reconstruct parts moving on the belt.")
    p_cap.add_argument("--serial-port", default="COM3", help="Hall-sensor serial port. Default: COM3.")
    p_cap.set_defaults(func=_cmd_capture)

    p_measure = subparsers.add_parser("measure-piece", help="Measure distances on a reconstruction.")
    p_measure.add_argument("name", help="Reconstruction name without extension, e.g. IR1.")
    p_measure.set_defaults(func=_cmd_measure_piece)

    return parser


# --- helpers ----------------------------------------------------------------
def _calibration(storage: StorageLayout) -> CameraCalibration:
    return load_calibration(storage.calibration_file)


def _ground_sampling(
    config: CameraConfig, calibration: CameraCalibration, storage: StorageLayout
) -> GroundSampling:
    height_mm = load_height_mm(storage.height_file)
    optics = compute_optical_parameters(calibration, config)
    return compute_ground_sampling(optics, config, height_mm)


# --- command handlers -------------------------------------------------------
def _cmd_calibrate(args: argparse.Namespace, config: CameraConfig, storage: StorageLayout) -> None:
    image_dir = Path(args.image_dir) if args.image_dir else storage.base_dir / "calibration_images"
    run_chessboard_calibration(config, storage.calibration_file, image_dir)


def _cmd_visualize(_args: argparse.Namespace, config: CameraConfig, _storage: StorageLayout) -> None:
    from .tools import visualize_camera

    visualize_camera(config)


def _cmd_position(_args: argparse.Namespace, config: CameraConfig, storage: StorageLayout) -> None:
    from .tools import position_camera

    position_camera(config, _calibration(storage))


def _cmd_measure_height(
    _args: argparse.Namespace, config: CameraConfig, storage: StorageLayout
) -> None:
    from .tools import measure_height

    measure_height(config, _calibration(storage), storage)


def _cmd_show_results(
    _args: argparse.Namespace, config: CameraConfig, storage: StorageLayout
) -> None:
    from .tools import show_results

    calibration = _calibration(storage)
    show_results(config, calibration, _ground_sampling(config, calibration, storage))


def _cmd_capture(args: argparse.Namespace, config: CameraConfig, storage: StorageLayout) -> None:
    from .capture import PieceCaptureSession

    calibration = _calibration(storage)
    ground = _ground_sampling(config, calibration, storage)
    PieceCaptureSession(config, calibration, ground, storage, serial_port=args.serial_port).run()


def _cmd_measure_piece(
    args: argparse.Namespace, config: CameraConfig, storage: StorageLayout
) -> None:
    from .measurement import measure_reconstruction

    calibration = _calibration(storage)
    measure_reconstruction(args.name, _ground_sampling(config, calibration, storage), storage)


if __name__ == "__main__":
    raise SystemExit(main())
