"""Core input primitives (Layer 2). Raw + humanized variants.

`*_raw` are deterministic and emit detectable signatures (zero-duration taps,
straight-line swipes). They MUST NOT be wired into commands by default;
the humanized variants are the default Layer 2 surface.
"""

from __future__ import annotations

import os
import random
import shlex
import time
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import ime as _ime
from mobilecli.safety import humanize as _hz


def tap_raw(device: Device, x: int, y: int) -> dict[str, Any]:
    device.shell(f"input tap {x} {y}")
    return {"x": x, "y": y, "duration_ms": 0}


def tap_humanized(
    device: Device,
    *,
    bounds: tuple[int, int, int, int] | None = None,
    x: int | None = None,
    y: int | None = None,
) -> dict[str, Any]:
    """Humanized tap.

    Either pass `bounds` (jitter within inner 60%) or `(x, y)` (±8 px jitter).
    Uses `input swipe X Y X Y dur` so the touch has a measurable duration --
    `input tap` is duration=0 and that itself is a bot signature.
    """
    if bounds is not None:
        tx, ty = _hz.jittered_tap_point(bounds)
    elif x is not None and y is not None:
        tx, ty = _hz.jittered_xy(x, y)
    else:
        raise ValueError("tap_humanized needs bounds or (x, y)")
    duration_ms = _hz.log_normal_duration_ms()
    device.shell(f"input swipe {tx} {ty} {tx} {ty} {duration_ms}")
    return {"x": tx, "y": ty, "duration_ms": duration_ms}


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


def _screen_wh(device: Device) -> tuple[int, int]:
    try:
        out = device.shell("wm size")
        import re as _re
        m = _re.search(r"(\d+)x(\d+)", out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:  # noqa: BLE001
        pass
    return (1080, 2410)


def swipe_humanized(device: Device, start, end) -> dict[str, Any]:
    """Humanized swipe.

    Default: straight `input swipe` with randomized 0.8~2.0s duration + ±4px
    endpoint jitter (works on all devices, beats the old fixed 0.6~1.2s line).

    Opt-in `EM_CURVED_SWIPE=1`: try a continuous bezier gesture via sendevent
    (needs a touch device writable from `adb shell` -- effectively rooted
    devices; on non-root Android `sendevent /dev/input/*` is Permission denied).
    Any failure falls back to the straight line below, so it never degrades.
    """
    pts = _hz.bezier_swipe_points(start, end, n_points=24)
    dur = _hz.swipe_duration_s()
    if os.environ.get("EM_CURVED_SWIPE") == "1":
        from mobilecli.core import touch as _touch

        info = _touch.probe_touch_device(device)
        if info is not None:
            res = _touch.curved_swipe(device, pts, dur, _screen_wh(device), info)
            if res is not None:
                return {"mode": "curved", **res}
    sx, sy = _hz.jittered_xy(start[0], start[1], radius=4)
    ex, ey = _hz.jittered_xy(end[0], end[1], radius=4)
    device.shell(f"input swipe {sx} {sy} {ex} {ey} {int(dur * 1000)}")
    return {
        "mode": "line",
        "x1": sx, "y1": sy, "x2": ex, "y2": ey,
        "duration_ms": int(dur * 1000),
    }


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


def type_text_humanized(device: Device, text: str) -> dict[str, Any]:
    """Humanized type. ASCII: per-char with log-normal delay. CJK: clipboard via
    ADBKeyboard broadcast + 200-600 ms post-paste dwell.
    """
    if text.isascii():
        for ch in text:
            escaped = ch.replace(" ", "%s")
            device.shell(f"input text {shlex.quote(escaped)}")
            time.sleep(_hz.per_char_type_delay_s())
        return {"chars": len(text), "mode": "input"}
    prev = _ime.current_ime(device)
    _ime.set_adbkeyboard(device)
    try:
        device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(text)}")
        time.sleep(random.uniform(0.2, 0.6))
        return {"chars": len(text), "mode": "adbkeyboard"}
    finally:
        _ime.restore_ime(device, prev)
