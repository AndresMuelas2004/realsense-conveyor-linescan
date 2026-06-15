# Operator guide

The detailed, physically grounded version of the workflow. Commands are run as
`linescan <command>`. Steps 1–5 commission a station and rarely change afterwards;
steps 6–7 are the everyday use.

---

## 1. Calibrate (`linescan calibrate`)

Run only when deploying or changing a camera. Each camera has slightly different
intrinsics (focal length, optical center), and the rest of the system depends on
them being accurate.

Print a chessboard, lay it on a flat surface, and with the camera connected:

- Press **`s`** to grab a view. Capture the board from many angles and distances —
  20 or more; more is better.
- Press **`q`** to finish; OpenCV computes the intrinsic matrix and distortion
  coefficients and saves them to `data/calibration/chessboard_calibration.npz`.

The default board is `8 x 5` inner corners at `27 mm` per square (override with
`--image-dir` for where views are stored).

## 2. Align with the belt (`linescan visualize`)

Opens a live preview. The camera's **vertical axis must be parallel to the belt's
direction of travel**, otherwise stacked strips drift sideways.

Rotate the camera until the metal edges of the belt run parallel to the window
borders. For a precise check, capture a part later (step 6) and zoom into where two
strips meet in `measure-piece` (step 7): the pixels should line up. Once aligned,
do not touch the camera again.

## 3. Level over the belt (`linescan position`)

Prints the depth at four points equidistant from the optical center — two on the
vertical axis (`VVV`), two on the horizontal (`HHH`). If the camera is parallel to
the belt, each pair reads the same.

Adjust tilt until both pairs differ by **less than ~1 mm over ten consecutive
prints**. Do this over the belt, under good lighting, for trustworthy depth.

## 4. Measure the height (`linescan measure-height`)

Measures the distance from the optical center down to the surface beneath it. Place
the **top surface of a part** under the camera and measure to that surface.

It takes the **median of 100 readings** (each after discarding a few frames so depth
settles) for robustness, then stores it in `data/state/height_mm.npy`. Every
mm-per-pixel calculation derives from this height, so measure it carefully.

## 5. Review the parameters (`linescan show-results`)

A read-only print-out (no camera needed) of the operator-entered values and
everything derived from them: sensor size, focal lengths, mm-per-pixel on each
axis, and the observable plane at the measured height. Use it to sanity-check the
calibration and height before capturing. You can verify mm-per-pixel physically:
the "observable plane" should match what you measure on the belt with a ruler.

## 6. Capture (`linescan capture`)

The main program. Start the belt at — or just before — launching this, to avoid
edge cases.

What happens:

1. It prints which camera is connected and a short usage note.
2. With the belt running, it continuously times one full revolution of the encoder.
   After 7 revolutions it reports the first belt speed (a rolling mean of the last 5)
   and keeps updating it every revolution, so you can vary the belt speed live.
3. When you see **`___ Parts may now pass ___`**, the belt depth has been measured
   and parts can start flowing. (The first frames are spent measuring belt depth; a
   part present during that window would confuse detection.)
4. It continuously prints the belt speed and revolution time. Empirically, capture
   quality is best around revolution times of **0.65–0.8 s**.
5. For each part, it prints `Reconstruction number: X` and writes `IRX.png` (color)
   and `IRPX.png` (depth) to `reconstructions/`, with the contributing strips under
   `strips/IRX/`.
6. Press **`q`** to stop. On exit it logs the run parameters and copies the
   reconstructions into `history/`.

Use `--serial-port` if the microcontroller is not on `COM3`.

**Troubleshooting.** If you see `Hall sensor measurement error`, a pulse was missed;
restart the capture. If the belt runs faster than ~320–330 mm/s the sensor stops
detecting reliably — fit a larger encoder roller.

## 7. Measure a part (`linescan measure-piece IR<n>`)

Opens a reconstruction by name (e.g. `IR1`). Controls:

- **Mouse wheel** — zoom in/out (the pixel under the cursor stays anchored).
- **Right-click + drag** — pan.
- **Left-click two points** — prints the pixel distance (horizontal and vertical)
  and the real distance in centimetres. Point pairs alternate green/red.

Press any key to close. Accuracy depends on the reconstruction quality and on a
good height and alignment — see *Limitations* in the [README](../README.md).

---

## Why strips overlap, and how the overlap is removed

There is a delay between *ordering* a capture and the *frame* the camera actually
returns (the most recent one it has). That delay shifts the captured strip relative
to where the belt actually is. Part of the shift would create **overlap** between
consecutive strips, and part would create **gaps**.

Gaps are unrecoverable — that area of the part was simply never imaged. Overlap, on
the other hand, can be measured and removed. So the system deliberately captures a
little **early** (the configured interval minus a small margin), guaranteeing
overlap instead of gaps, measures the timing offset to both the previous and the
next capture, converts the overlapping time into millimetres via the belt speed,
and trims that many rows off the bottom of the strip.

This trimmed-row count depends only on the timing offsets and the belt speed — it is
**independent of the strip size and of the pixel scale**. A fractional result is
rounded **down** on purpose: trimming one row too few leaves a harmless sliver of
overlap, while trimming one too many would reopen an uncoverable gap.
