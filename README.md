# RealSense Conveyor Line-Scan

Turn an **Intel RealSense depth camera into a synchronized line-scan scanner** for
objects travelling on a conveyor belt: reconstruct a clean image of every part as
it passes, then measure real-world distances on it.

> MIT licensed · Python 3.10+ · OpenCV + Intel RealSense SDK 2.0

---

## The idea

An area camera looking down at a moving belt sees each part distorted by motion
and only for a handful of frames. A **line-scan** camera instead reads one thin
line at a time and stacks those lines into a continuous image as the object moves
underneath — the way a flatbed scanner or a fax machine builds an image.

This project emulates a line-scan camera with an ordinary RealSense D405:

1. From every frame it keeps only a **thin central strip** (least affected by
   perspective).
2. A **Hall-effect sensor** watching a magnet on the encoder roller measures the
   **belt speed**, which sets exactly how often a strip must be captured.
3. Because capture timing jitters by milliseconds, consecutive strips slightly
   **overlap**; the overlap is computed from the timing offsets and trimmed, so
   strips join seamlessly instead of leaving gaps.
4. Depth is used to **detect when a part enters and leaves** the field of view, so
   each part becomes its own reconstruction.
5. The result is one stitched **color** image (`IR<n>.png`) and one **depth**
   image (`IRP<n>.png`) per part, which you can open and **measure** in real units.

```
            Intel RealSense D405  (color + depth, looking down)
                         │
                         │   keep a central strip, N px tall, every frame
                         ▼
   ┌───────────────────────────────────────────────┐
   │ ▓▓▓▓▓▓▓▓  part  ▓▓▓▓▓▓▓▓                        │ ── belt travel ──▶
   └───────────────────────────────────────────────┘
        ▲
        └─ Hall sensor + magnet on the encoder roller  →  belt speed

   strips captured over time            stacked into one reconstruction
   ┌───────────────┐  ┐
   ├───────────────┤  │   trim the
   ├───────────────┤  ├─ overlap  ─▶   ┌───────────────┐
   ├───────────────┤  │                │               │
   └───────────────┘  ┘                │   IR<n>.png    │
                                       │   IRP<n>.png   │
                                       └───────────────┘
```

## Hardware

- **Intel RealSense D405** (any RealSense with color + depth works; the D405 is
  what this was built and calibrated for), connected over USB.
- A conveyor belt with an **encoder roller** carrying a **neodymium magnet**.
- A microcontroller (e.g. **ESP32**) wired to a **Hall-effect sensor**, sending two
  one-line markers over serial: `bb` when the magnet approaches and `hh` on
  detection. Default link: `COM3` at `115200` baud.

The software imports `pyrealsense2`, `pyserial` and `keyboard` **lazily**, so you
can install it, run the tests and use the offline parts without any of that
hardware attached.

## Installation

```powershell
# from the project root, in a virtual environment
pip install -e .
# for development (tests, linting, type-checking)
pip install -e ".[dev]"
```

This exposes a single console command, `linescan`, plus `python -m linescan`.

## Operator workflow

Each step is one subcommand. Steps 1–5 are commissioning (done once when placing a
camera); steps 6–7 are the everyday use. Run `linescan <command> --help` for
options.

| # | Command | Purpose |
|---|---------|---------|
| 1 | `linescan calibrate` | Chessboard intrinsic calibration. Only when the camera changes. |
| 2 | `linescan visualize` | Live preview to align the camera's vertical axis with the belt. |
| 3 | `linescan position` | Print symmetric depth readings to level the camera over the belt. |
| 4 | `linescan measure-height` | Measure and store the camera height above the surface. |
| 5 | `linescan show-results` | Print every derived parameter for a sanity check. |
| 6 | `linescan capture` | Run the belt, reconstruct each part that passes. |
| 7 | `linescan measure-piece IR1` | Open a reconstruction and click two points to measure. |

A typical commissioning session and run:

```powershell
linescan calibrate              # once per camera; press 's' ~20+ times, then 'q'
linescan visualize              # rotate the camera until the belt edges are parallel
linescan position               # adjust tilt until each V/H pair reads within ~1 mm
linescan measure-height         # place the part surface under the camera, wait
linescan show-results           # verify the numbers look sane
linescan capture                # start the belt at/just before this; 'q' to stop
linescan measure-piece IR1      # measure distances on the first reconstruction
```

See [`docs/operator-guide.md`](docs/operator-guide.md) for the detailed, physically
grounded version of each step, and [`docs/architecture.md`](docs/architecture.md) for
the code layout and how it maps to the original prototype.

## Key concepts

**mm-per-pixel.** From the intrinsic calibration and the measured height, similar
triangles give the real size of the plane the camera sees, and dividing by the
pixel counts gives millimetres per pixel — separately for the horizontal and
vertical axes, since they differ. Every real-world measurement comes from these.

**Overlap removal.** Captures are taken slightly *early* (interval minus a small
margin) to force overlap rather than gaps — a gap is unrecoverable, an overlap is
not. The overlap in time is reconstructed from the per-capture timing offsets,
converted to millimetres via the belt speed, and trimmed off the bottom of each
strip. Crucially the trimmed row count depends only on timing and speed, **not** on
the pixel scale (a property the test-suite pins down).

**Part detection.** The belt's reference depth is measured once from a few early
frames. A part is considered present while points on the strip rise between a
minimum threshold and half the belt depth above the belt (the upper bound rejects
the spurious zero-depth readings the sensor occasionally returns).

## Configuration

Defaults live in `CameraConfig` (`src/linescan/config.py`) and reproduce the
original D405 deployment:

| Field | Default | Meaning |
|-------|---------|---------|
| `width_px` / `height_px` | 1280 / 720 | Stream resolution. |
| `pixel_size_mm` | 0.003 | Physical pixel pitch (estimate; cancels out of mm-per-pixel). |
| `fps` | 30 | Frame rate. |
| `exposure_us` | 2000 | Manual exposure during capture. |
| `roller_encoder_diameter_mm` | 63.6 | Encoder roller diameter (raise it for higher belt speeds). |
| `captured_vertical_pixels` | 100 | Central strip height; keep it ≳ 80–100. |
| `fov_horizontal_deg` / `fov_vertical_deg` | 87 / 58 | Informational only. |

## Output

Written under the working directory (override with `--base-dir`):

| Path | Contents |
|------|----------|
| `reconstructions/IR<n>.png` | Stitched color image of part *n*. |
| `reconstructions/IRP<n>.png` | Stitched depth image of part *n*. |
| `strips/IR<n>/` | The individual strips that built reconstruction *n*. |
| `history/` | Every reconstruction copied here, numbered, across runs. |
| `camera_parameters_log.json` | One JSON-Lines record of parameters per run. |

Calibration and measured state live under `data/` (override with `--data-dir`):
`data/calibration/chessboard_calibration.npz` and `data/state/height_mm.npy` are
committed as a **working example**, so `show-results`, the tests and the geometry
work out of the box.

## Limitations & accuracy

Reconstruction and measurement accuracy depend on three things (in order of impact):

1. **Belt-speed measurement.** The Hall sensor is far better than the bare encoder
   it replaced, but still varies by hundredths of a second. Above ~320–330 mm/s it
   misses pulses; a **larger encoder roller** raises that ceiling. For exact
   metrology an absolute encoder or a laser linear-speed sensor would be ideal.
2. **mm-per-pixel.** Very accurate in practice (sub-millimetre across the whole
   plane, verified against a ruler), but it relies on a stable measured height — a
   camera with a hardware trigger and repeatable depth would remove the need to
   average.
3. **Capture-vs-frame timing offset.** Handled by the overlap-removal step, but
   never perfect: residual sub-millisecond offsets remain, and trimmed rows are
   rounded down to avoid uncoverable gaps.

This is excellent for detecting features such as holes and for approximate
dimensions; for tight-tolerance geometry, upgrade items 1 and 3 above.

## Development

```powershell
pytest        # geometry parity, overlap logic, import-without-hardware
ruff check .  # lint
mypy src      # type-check
```

The geometry tests assert **bit-for-bit parity** with the original program, using
golden values captured from the original's own calculation modules.

## License

[MIT](LICENSE) © 2026 Andres Muelas
