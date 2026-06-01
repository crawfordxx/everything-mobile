from __future__ import annotations
from pathlib import Path
from mobilecli.core import touch

FIX = Path(__file__).parent.parent / "fixtures"


def test_parse_getevent_picks_touch_device():
    out = (FIX / "getevent-touch.txt").read_text()
    info = touch.parse_getevent(out)
    assert info == {"event_node": "/dev/input/event1", "x_max": 12799, "y_max": 28559}


def test_parse_getevent_none_when_no_touch():
    info = touch.parse_getevent('add device 1: /dev/input/event0\n  name: "gpio_keys"\n')
    assert info is None
