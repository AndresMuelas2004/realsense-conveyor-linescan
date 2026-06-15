# Architecture

This project is a ground-up rewrite of an earlier prototype. The behavior — every
formula, threshold and output file — is preserved; the structure is not. This
document explains the layout, how it maps to the original scripts, and the design
decisions behind the changes.

## Layers

```
config        static parameters + storage paths (no I/O, no hardware)
geometry      pure optics/measurement math (the tested core)
calibration   load / produce intrinsic calibration
state         persisted runtime values (height, belt speed, interval)
camera        RealSense pipeline wrapper            ─┐
hall_sensor   belt-speed sensing thread             ─┤ hardware (lazy imports)
reconstruction strip overlap, belt depth, stitching ─┘
capture       the per-part capture state machine
measurement   interactive distance viewer
report        per-run parameter log
archive       copy reconstructions into history
tools/        operator setup commands
cli           argparse front-end → `linescan`
```

Dependencies point downward: `capture` orchestrates `camera`, `hall_sensor`,
`reconstruction`, `report` and `archive`; everything ultimately rests on the pure
`geometry` + `config` core.

## Mapping from the original

| Original script | New home |
|-----------------|----------|
| `PARAMETROS_METER_USUARIO.py` | `config.CameraConfig` |
| `CalculoParametrosNecesarios.py` | `geometry.compute_optical_parameters` |
| `FOVtotal.py` | `geometry.compute_ground_sampling` |
| `DiferenciaDistancias.py` | `geometry.pixel_distance_mm` |
| `CargarAltura.py` | `state.load_height_mm` |
| `Calibración/.../ParámetrosUltimaCalibracion.py` | `calibration.load_calibration` |
| `Calibración/.../CalibracionPorAjedrez.py` | `calibration.run_chessboard_calibration` |
| `MEDIR_ALTURA.py` | `tools.measure_height` |
| `POSICIONAR_CAMARA.py` | `tools.position_camera` |
| `VISUALIZACION_CAMARA.py` | `tools.visualize_camera` |
| `MOSTRAR_RESULTADOS.py` | `tools.show_results` |
| `sensorHall.py` | `hall_sensor.BeltSpeedSensor` |
| `CAPTURAR_IMAGENES.py` | `capture.PieceCaptureSession` |
| `HilosCapturaImagen.py` | `reconstruction.{stitch_color,stitch_depth,save_strip}` |
| `MEDIR_PIEZA_RECONSTRUIDA.py` | `measurement` |
| `FicheroJson.py` | `report.write_parameter_log` |
| `GuardarReconstrucciones.py` | `archive.archive_reconstructions` |

## Key design decisions

**No import-time side effects.** In the original, importing a module ran
computations, read files, or even opened the camera (`import FicheroJson` was used
to *execute* it). Here every module is import-safe; work happens only when a
function is called. `tests/test_imports.py` enforces this.

**Lazy hardware imports.** `pyrealsense2`, `pyserial` and `keyboard` are imported
inside the functions that need them, so the package installs, imports and tests
cleanly on a machine with no camera, no serial device and no elevated privileges.

**Encapsulated state.** The capture loop's ~25 module-level globals became named
attributes of `PieceCaptureSession`; the Hall sensor's shared global list became a
lock-guarded field of `BeltSpeedSensor`. Same data flow, no global mutation.

**Pure, tested geometry.** The measurement math is isolated in `geometry` and
covered by exact-parity tests (`tests/test_geometry.py`) whose golden values were
captured from the original program's own calculation modules.

**Renamed paths (English).** The on-disk names were translated:

| Original | New |
|----------|-----|
| `ImagenesReconstruidas/` | `reconstructions/` |
| `Imagenes guardadas/` | `strips/` |
| `HISTORIAL RECONSTRUCCIONES/` | `history/` |
| `altura_guardada.npy` | `data/state/height_mm.npy` |
| `VelocidadCinta.npz` | `data/state/belt_speed.npz` |
| `TiempoEntreFoto.npz` | `data/state/photo_interval.npz` |
| `parametros_camara.json` | `camera_parameters_log.json` |
| `parametros_calibracion.npz` | `data/calibration/chessboard_calibration.npz` |

Strip files `imagen_color_<n>.png` / `imagen_profunda_<n>.png` became
`color_<n>.png` / `depth_<n>.png`.

## Behavior-preserving fixes

A few original quirks were corrected without changing any result:

- **Shutdown camera conflict.** The original logged parameters (which opens its own
  camera session) while the capture pipeline was still running — two sessions on one
  device. Here the capture camera is released *before* the parameter log runs.
- **Unbounded growth.** A tracking list grew on every frame while only its last
  element was ever read (and all elements aliased the same cleared list). It is
  gone; only the current frame's rows are used, exactly as before.
- **Parameter log format.** The original appended indented JSON objects, producing a
  file that was not valid JSON as a whole. It is now JSON Lines — append-only and
  fully parseable — with the same fields.
- **Robust state loading.** Missing `belt_speed`/`photo_interval` files yield `None`
  in the log instead of crashing.

## Deliberately preserved quirk

`geometry` reproduces the original mm-per-pixel derivation exactly, including the
fact that it samples the ground plane on a `numpy.arange(-half, half + 0.1, 0.1)`
grid that overshoots the half-extent by up to one step. A clean `2 * half_extent`
would differ only around the 5th significant figure (sub-micron per pixel), but the
requirement was identical results, so the grid behavior is kept and documented in
`geometry._captured_span_mm`.
