"""Core input primitives (Layer 2). Raw versions; humanization wraps these in Phase B."""

from __future__ import annotations

import shlex
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import ime as _ime


def tap_raw(device: Device, x: int, y: int) -> dict[str, Any]:
    device.shell(f"input tap {x} {y}")
    return {"x": x, "y": y, "duration_ms": 0}


def swipe_raw(
    device: Device,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int,
) -> dict[str, Any]:
    device.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration_ms": duration_ms}


def keyevent_raw(device: Device, code: int | str) -> dict[str, Any]:
    device.shell(f"input keyevent {code}")
    return {"code": str(code)}


def type_text_raw(device: Device, text: str) -> dict[str, Any]:
    """Type text. ASCII -> `input text`; CJK / emoji -> ADBKeyboard broadcast."""
    if text.isascii():
        escaped = text.replace(" ", "%s")
        device.shell(f"input text {shlex.quote(escaped)}")
        return {"chars": len(text), "mode": "input"}
    prev = _ime.current_ime(device)
    _ime.set_adbkeyboard(device)
    try:
        device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(text)}")
        return {"chars": len(text), "mode": "adbkeyboard"}
    finally:
        _ime.restore_ime(device, prev)
