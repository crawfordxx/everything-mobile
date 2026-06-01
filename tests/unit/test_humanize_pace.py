from __future__ import annotations
from mobilecli.safety import humanize as hz


def test_pace_delay_in_range():
    xs = [hz.pace_delay_s(2.0, 10.0) for _ in range(2000)]
    assert all(2.0 <= x <= 10.0 for x in xs)
    assert 5.0 < sum(xs) / len(xs) < 7.0


def test_swipe_duration_range():
    xs = [hz.swipe_duration_s() for _ in range(500)]
    assert all(0.8 <= x <= 2.0 for x in xs)


def test_micro_wobble_returns_two_points():
    start, end = hz.micro_wobble_swipe(center_y=1200, screen_h=2410)
    assert len(start) == 2 and len(end) == 2
    assert start[0] == end[0]
    assert start != end
