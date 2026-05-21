"""Tests for humanize timing and jitter primitives."""

from __future__ import annotations

import statistics

from mobilecli.safety.humanize import (
    bezier_swipe_points,
    human_delay_s,
    jittered_tap_point,
    jittered_xy,
    log_normal_duration_ms,
    per_char_type_delay_s,
    read_pause_s,
)


def test_human_delay_distribution_has_variance():
    samples = [human_delay_s() for _ in range(500)]
    assert all(0.3 <= s <= 8.0 for s in samples)
    assert statistics.stdev(samples) > 0.1


def test_jittered_tap_point_inside_inner_60_percent_box():
    bounds = (100, 200, 300, 400)  # inner-60% = (140,240)-(260,360)
    for _ in range(200):
        x, y = jittered_tap_point(bounds)
        assert 140 <= x <= 260
        assert 240 <= y <= 360


def test_jittered_tap_point_is_not_always_center():
    bounds = (100, 200, 300, 400)
    points = {jittered_tap_point(bounds) for _ in range(100)}
    assert len(points) > 50


def test_jittered_xy_within_radius():
    for _ in range(200):
        x, y = jittered_xy(540, 1200, radius=8)
        assert abs(x - 540) <= 8
        assert abs(y - 1200) <= 8


def test_log_normal_duration_ms_centered_near_90():
    samples = [log_normal_duration_ms() for _ in range(500)]
    assert 30 <= statistics.median(samples) <= 200
    assert all(s >= 10 for s in samples)


def test_bezier_swipe_points_returns_30_plus_points():
    pts = bezier_swipe_points((100, 200), (500, 1000))
    assert len(pts) >= 30
    assert pts[0] == (100, 200)


def test_bezier_swipe_has_lateral_wobble():
    # Vertical target line; interior points should jitter laterally
    pts = bezier_swipe_points((100, 200), (100, 1000))
    xs = [p[0] for p in pts[5:-5]]
    assert max(xs) - min(xs) >= 4


def test_read_pause_first_screen_is_long():
    p = read_pause_s(text_length=200, seen_recently=False)
    assert 1.5 <= p <= 5.0


def test_read_pause_recently_seen_is_short():
    p = read_pause_s(text_length=200, seen_recently=True)
    assert 0.3 <= p <= 1.2


def test_per_char_type_delay_positive():
    samples = [per_char_type_delay_s() for _ in range(100)]
    assert all(s > 0 for s in samples)
    assert statistics.median(samples) > 0
