"""UI parsing helpers (Layer 2).

Parses `uiautomator dump` XML to find elements by resource-id, content-desc,
text, or class. Returns dicts with center coordinates ready for tap.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.envelope import EmError, ErrorCode

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def parse_bounds(s: str) -> tuple[int, int, int, int] | None:
    m = _BOUNDS_RE.match(s)
    if not m:
        return None
    return (int(m[1]), int(m[2]), int(m[3]), int(m[4]))


def _node_to_dict(node: ET.Element) -> dict[str, Any]:
    bounds_s = node.get("bounds", "")
    bounds = parse_bounds(bounds_s)
    cx = cy = -1
    if bounds is not None:
        cx = (bounds[0] + bounds[2]) // 2
        cy = (bounds[1] + bounds[3]) // 2
    return {
        "resource_id": node.get("resource-id", ""),
        "content_desc": node.get("content-desc", ""),
        "text": node.get("text", ""),
        "class": node.get("class", ""),
        "bounds": list(bounds) if bounds else None,
        "cx": cx,
        "cy": cy,
        "clickable": node.get("clickable") == "true",
        "focused": node.get("focused") == "true",
    }


def _iter_nodes(xml: str) -> Iterator[ET.Element]:
    root = ET.fromstring(xml)
    yield from root.iter("node")


def find_by_resource_id(xml: str, resource_id: str) -> dict[str, Any] | None:
    for node in _iter_nodes(xml):
        if node.get("resource-id") == resource_id:
            return _node_to_dict(node)
    return None


def find_by_content_desc(xml: str, content_desc: str) -> dict[str, Any] | None:
    for node in _iter_nodes(xml):
        if node.get("content-desc") == content_desc:
            return _node_to_dict(node)
    return None


def find_by_text(xml: str, text: str) -> dict[str, Any] | None:
    for node in _iter_nodes(xml):
        if node.get("text") == text:
            return _node_to_dict(node)
    return None


def find_all_by_resource_id(xml: str, resource_id: str) -> list[dict[str, Any]]:
    return [
        _node_to_dict(node) for node in _iter_nodes(xml) if node.get("resource-id") == resource_id
    ]


def dump(
    device: Device,
    output_path: str | None = None,
    retry: int = 4,
) -> dict[str, Any]:
    """Run `uiautomator dump`, pull XML to local path.

    `uiautomator dump` fails with "could not get idle state" when the screen
    is animating continuously (e.g. Douyin home autoplays video). The dump
    process exits 0 but no file is written to /sdcard/em.xml, so the only
    reliable success signal is "pull succeeded AND file > 100 bytes".

    Recovery escalates: bare → tap-pause low → tap-pause higher → dpad-center →
    tiny nudge swipe. Between attempts we also delete any stale dump file.
    """
    if output_path is None:
        output_path = f"/tmp/em-dump-{int(time.time() * 1000)}.xml"

    def _try_dump() -> int | None:
        try:
            device.shell("rm -f /sdcard/em.xml")
            device.shell("uiautomator dump --compressed /sdcard/em.xml")
            device.pull("/sdcard/em.xml", output_path)
            size = Path(output_path).stat().st_size
            return size if size > 100 else None
        except (EmError, FileNotFoundError, OSError):
            return None

    recovery_steps: list[tuple[str, float]] = [
        ("", 0.0),
        ("input tap 540 1100", 0.9),
        ("input tap 540 800", 1.0),
        ("input keyevent KEYCODE_DPAD_CENTER", 1.2),
        ("input swipe 540 1500 540 1490 100", 1.4),
    ]
    for attempt in range(min(retry + 1, len(recovery_steps))):
        cmd, sleep_s = recovery_steps[attempt]
        if cmd:
            try:
                device.shell(cmd)
            except EmError:
                pass
            time.sleep(sleep_s)
        size = _try_dump()
        if size is not None:
            return {"path": output_path, "size": size}
    raise EmError(
        ErrorCode.UNKNOWN,
        "uiautomator dump failed after all recovery attempts",
        hint=(
            "screen may be animating continuously; try `mobilecli screenshot` to see current state"
        ),
    )
