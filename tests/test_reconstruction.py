"""Tests for the pure reconstruction helpers.

Expectations are derived from first principles, not from the code's output:

* Overlap removal: substituting belt_speed = mm_per_pixel_v * pixels / interval
  into the original formula makes mm_per_pixel_v cancel, so the trimmed row count
  reduces to ``int(pixels * overlap_time / interval)`` and must NOT depend on the
  pixel scale — a property the original author documented explicitly.
* Belt depth: the reference depth is the mean of every sample point.
"""

from __future__ import annotations

from linescan.reconstruction import belt_depth_from_samples, compute_overlap_pixels


def _expected_overlap(pixels, overlap_time, interval):
    return int(pixels * overlap_time / interval)


def test_overlap_first_capture_uses_zero_history():
    # len(offsets) == 1 -> previous advance/offset treated as 0.
    margin, advance_now, offset_now, interval, pixels = 0.1, 0.0, 0.025, 0.3, 100
    overlap_time = margin - advance_now + offset_now
    expected = _expected_overlap(pixels, overlap_time, interval)

    result = compute_overlap_pixels([advance_now], [offset_now], interval, margin, 0.3, pixels)
    assert result == expected
    assert result == 41  # sanity: well away from an integer boundary


def test_overlap_is_independent_of_pixel_scale():
    # The documented contract: trimmed rows depend only on timing and belt speed,
    # never on mm-per-pixel. Two very different scales must give the same answer.
    advances, offsets, interval, margin, pixels = [0.02, 0.01], [0.001, 0.003], 0.2, 1 / 30, 100
    coarse = compute_overlap_pixels(advances, offsets, interval, margin, 0.30, pixels)
    fine = compute_overlap_pixels(advances, offsets, interval, margin, 0.95, pixels)
    assert coarse == fine


def test_overlap_with_history():
    advances = [0.02, 0.01]
    offsets = [0.001, 0.003]
    margin, interval, pixels = 1 / 30, 0.2, 100
    overlap_time = margin + advances[-2] - advances[-1] + offsets[-1] - offsets[-2]
    expected = _expected_overlap(pixels, overlap_time, interval)

    result = compute_overlap_pixels(advances, offsets, interval, margin, 0.3, pixels)
    assert result == expected
    assert result == 22


def test_overlap_truncates_toward_zero():
    # The result is an int() of the row count, i.e. the fractional part is
    # dropped (truncated, not rounded). overlap_time chosen so the exact count
    # is 41.5 rows -> 41.
    margin, advance_now, offset_now, interval, pixels = 0.083, 0.0, 0.0, 0.2, 100
    overlap_time = margin - advance_now + offset_now
    assert _expected_overlap(pixels, overlap_time, interval) == 41  # 100*0.083/0.2 = 41.5

    result = compute_overlap_pixels([advance_now], [offset_now], interval, margin, 0.3, pixels)
    assert result == 41


def test_overlap_can_be_negative_when_capture_runs_late():
    # If a capture is late rather than early, the formula yields a negative trim;
    # it is intentionally NOT clamped to zero (faithful to the original).
    advances, offsets, interval, margin, pixels = [0.0, 0.5], [0.0, 0.0], 0.2, 0.01, 100
    overlap_time = margin + advances[-2] - advances[-1] + offsets[-1] - offsets[-2]
    expected = _expected_overlap(pixels, overlap_time, interval)

    result = compute_overlap_pixels(advances, offsets, interval, margin, 0.3, pixels)
    assert result == expected
    assert result == -245


def test_belt_depth_is_mean_of_all_samples():
    assert belt_depth_from_samples([[10, 20], [30, 40]]) == 25.0
    assert belt_depth_from_samples([[100.0, 100.0, 100.0]] * 5) == 100.0
    assert belt_depth_from_samples([[0, 70]]) == 35.0


def test_belt_depth_single_sample_equals_that_sample():
    assert belt_depth_from_samples([[12.5]]) == 12.5


def test_belt_depth_averages_across_rows_and_columns():
    # Every element contributes equally regardless of how it is grouped.
    assert belt_depth_from_samples([[1, 2, 3], [4, 5, 6]]) == 3.5


def test_belt_depth_returns_float():
    assert isinstance(belt_depth_from_samples([[1, 2, 3]]), float)
