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
