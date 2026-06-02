"""sendevent-based continuous (curved) swipe + touch-device probing."""

from __future__ import annotations

import re
from typing import Any

from mobilecli.adb.device import Device

_ADD_DEV_RE = re.compile(r"add device \d+:\s*(\S+)")
_ABS_X_RE = re.compile(r"ABS_MT_POSITION_X.*?max (\d+)")
_ABS_Y_RE = re.compile(r"ABS_MT_POSITION_Y.*?max (\d+)")


def parse_getevent(out: str) -> dict[str, Any] | None:
    """从 `getevent -lp` 全设备输出里挑出含 ABS_MT_POSITION_X 的触摸设备。"""
    blocks: list[tuple[str, str]] = []
    cur_node: str | None = None
    cur_lines: list[str] = []
    for line in out.splitlines():
        m = _ADD_DEV_RE.search(line)
        if m:
            if cur_node is not None:
                blocks.append((cur_node, "\n".join(cur_lines)))
            cur_node = m.group(1)
            cur_lines = []
        else:
            cur_lines.append(line)
    if cur_node is not None:
        blocks.append((cur_node, "\n".join(cur_lines)))
    for node, body in blocks:
        mx = _ABS_X_RE.search(body)
        my = _ABS_Y_RE.search(body)
        if mx and my:
            return {"event_node": node, "x_max": int(mx.group(1)), "y_max": int(my.group(1))}
    return None


def probe_touch_device(device: Device) -> dict[str, Any] | None:
    """运行 getevent -lp 并解析;失败返回 None(调用方回退直线)。"""
    try:
        out = device.shell("getevent -lp")
    except Exception:  # noqa: BLE001
        return None
    return parse_getevent(out)


# evdev numeric codes
_EV_SYN, _EV_KEY, _EV_ABS = 0, 1, 3
_SYN_REPORT = 0
_BTN_TOUCH, _BTN_TOOL_FINGER = 330, 325
_ABS_MT_SLOT, _ABS_MT_TRACKING_ID = 47, 57
_ABS_MT_POSITION_X, _ABS_MT_POSITION_Y = 53, 54
_TRACKING_ID = 4242


def _sendevent_permitted(device: Device, node: str) -> bool:
    """一次性廉价探测:发单条无副作用的 SYN_REPORT sendevent。

    非 root Android 写 /dev/input 会 "Permission denied"(非零退出)→ False,
    且**立即**返回(不含任何 sleep),让调用方在构造含大量 sleep 的完整手势链
    之前就快速回退,避免白跑一整串注定失败的 sleep。
    """
    try:
        device.shell(f"sendevent {node} {_EV_SYN} {_SYN_REPORT} 0", timeout_s=5)
    except Exception:  # noqa: BLE001
        return False
    return True


def curved_swipe(
    device: Device,
    points: list[tuple[int, int]],
    duration_s: float,
    screen_wh: tuple[int, int],
    touch_info: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """沿 points(屏幕坐标)发一条连续 type-B 多点手势(单条 adb shell sendevent 序列)。
    touch_info=None 或点数<2 -> 返回 None(回退)。"""
    if not touch_info or len(points) < 2:
        return None
    node = touch_info["event_node"]
    if not _sendevent_permitted(device, node):
        # 非 root 设备无法写 /dev/input;快速回退直线(不白跑整串 sleep)。
        return None
    xmax, ymax = int(touch_info["x_max"]), int(touch_info["y_max"])
    sw, sh = screen_wh

    def sx(x: int) -> int:
        return max(0, min(xmax, round(x * (xmax + 1) / sw)))

    def sy(y: int) -> int:
        return max(0, min(ymax, round(y * (ymax + 1) / sh)))

    def se(t: int, c: int, v: int) -> str:
        return f"sendevent {node} {t} {c} {v}"

    dt = max(0.005, duration_s / len(points))
    x0, y0 = points[0]
    parts: list[str] = [
        se(_EV_ABS, _ABS_MT_SLOT, 0),
        se(_EV_ABS, _ABS_MT_TRACKING_ID, _TRACKING_ID),
        se(_EV_KEY, _BTN_TOUCH, 1),
        se(_EV_KEY, _BTN_TOOL_FINGER, 1),
        se(_EV_ABS, _ABS_MT_POSITION_X, sx(x0)),
        se(_EV_ABS, _ABS_MT_POSITION_Y, sy(y0)),
        se(_EV_SYN, _SYN_REPORT, 0),
        f"sleep {dt:.3f}",
    ]
    for x, y in points[1:]:
        parts += [
            se(_EV_ABS, _ABS_MT_POSITION_X, sx(x)),
            se(_EV_ABS, _ABS_MT_POSITION_Y, sy(y)),
            se(_EV_SYN, _SYN_REPORT, 0),
            f"sleep {dt:.3f}",
        ]
    parts += [
        se(_EV_ABS, _ABS_MT_TRACKING_ID, 4294967295),
        se(_EV_KEY, _BTN_TOUCH, 0),
        se(_EV_KEY, _BTN_TOOL_FINGER, 0),
        se(_EV_SYN, _SYN_REPORT, 0),
    ]
    cmd = "; ".join(parts)
    try:
        device.shell(cmd, timeout_s=max(10, int(duration_s) + 8))
    except Exception:  # noqa: BLE001
        # sendevent on /dev/input often needs root (Permission denied on
        # non-rooted Android). Return None so the caller falls back to
        # `input swipe` (straight, but still humanized duration + jitter).
        return None
    return {"event_node": node, "points": len(points), "duration_s": duration_s}
