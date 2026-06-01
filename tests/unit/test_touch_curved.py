from __future__ import annotations
from mobilecli.core import touch


class _FakeDevice:
    def __init__(self):
        self.cmds = []

    def shell(self, cmd, timeout_s=30):
        self.cmds.append(cmd)
        return ""


def test_curved_swipe_builds_one_sendevent_command():
    dev = _FakeDevice()
    pts = [(100, 200), (150, 600), (200, 1000)]
    info = {"event_node": "/dev/input/event1", "x_max": 12799, "y_max": 28559}
    res = touch.curved_swipe(dev, pts, duration_s=1.0, screen_wh=(1080, 2410), touch_info=info)
    assert res is not None
    assert len(dev.cmds) == 1
    cmd = dev.cmds[0]
    assert cmd.count("sendevent /dev/input/event1") >= 3 * len(pts)
    assert "330 1" in cmd and "330 0" in cmd
    assert "sleep" in cmd
    assert "53 1185" in cmd or "53 1184" in cmd  # 100/1080*12800 ≈ 1185


def test_curved_swipe_none_without_touch_info():
    dev = _FakeDevice()
    res = touch.curved_swipe(dev, [(1, 2), (3, 4)], 1.0, (1080, 2410), touch_info=None)
    assert res is None
    assert dev.cmds == []
