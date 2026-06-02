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
    # 第一条是权限预探测(单条 SYN_REPORT),最后一条是完整手势链。
    assert len(dev.cmds) == 2
    probe, cmd = dev.cmds
    assert probe == "sendevent /dev/input/event1 0 0 0"
    assert "sleep" not in probe  # 探测必须不含 sleep(快速)
    assert cmd.count("sendevent /dev/input/event1") >= 3 * len(pts)
    assert "330 1" in cmd and "330 0" in cmd
    assert "sleep" in cmd
    assert "53 1185" in cmd or "53 1184" in cmd  # 100/1080*12800 ≈ 1185


def test_curved_swipe_none_without_touch_info():
    dev = _FakeDevice()
    res = touch.curved_swipe(dev, [(1, 2), (3, 4)], 1.0, (1080, 2410), touch_info=None)
    assert res is None
    assert dev.cmds == []


def test_curved_swipe_returns_none_on_shell_error():
    """sendevent 权限不足(非root)等 shell 报错 -> 返回 None(调用方回退直线)。"""

    class _RaisingDevice:
        def shell(self, cmd, timeout_s=30):
            raise RuntimeError("sendevent: Permission denied")

    info = {"event_node": "/dev/input/event1", "x_max": 12799, "y_max": 28559}
    res = touch.curved_swipe(_RaisingDevice(), [(1, 2), (3, 4)], 1.0, (1080, 2410), touch_info=info)
    assert res is None


def test_curved_swipe_denied_probe_skips_gesture_chain():
    """权限预探测失败时,不应再构造含大量 sleep 的完整手势链(避免白跑 ~8s)。"""

    class _DeniedDevice:
        def __init__(self):
            self.cmds = []

        def shell(self, cmd, timeout_s=30):
            self.cmds.append(cmd)
            raise RuntimeError("sendevent: /dev/input/event1: Permission denied")

    dev = _DeniedDevice()
    pts = [(100, 200), (150, 600), (200, 1000)]
    info = {"event_node": "/dev/input/event1", "x_max": 12799, "y_max": 28559}
    res = touch.curved_swipe(dev, pts, duration_s=1.0, screen_wh=(1080, 2410), touch_info=info)
    assert res is None
    # 只尝试了那一条探测命令,没有任何 sleep 链。
    assert len(dev.cmds) == 1
    assert "sleep" not in dev.cmds[0]
