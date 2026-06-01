"""Core Layer 2 screenshot helper."""

from __future__ import annotations

import io
import struct
import time
from pathlib import Path
from typing import Any

from mobilecli.adb.device import Device


def _png_dimensions(data: bytes) -> tuple[int, int]:
    """Read PNG width/height from IHDR. Returns (0, 0) on parse failure."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return (0, 0)
    if len(data) < 24:
        return (0, 0)
    width, height = struct.unpack(">II", data[16:24])
    return (width, height)


def capture(device: Device, output_path: str | None = None) -> dict[str, Any]:
    """Capture screenshot. Returns {path, size, width, height}."""
    if output_path is None:
        output_path = f"/tmp/em-screen-{int(time.time() * 1000)}.png"
    data = device.exec_out(["screencap", "-p"])
    Path(output_path).write_bytes(data)
    width, height = _png_dimensions(data)
    return {"path": output_path, "size": len(data), "width": width, "height": height}


def capture_region(
    device: Device,
    bounds: tuple[int, int, int, int],
    output_path: str | None = None,
) -> dict[str, Any]:
    """Screencap full screen, crop to `bounds` (x1,y1,x2,y2), save PNG."""
    from PIL import Image  # local import: optional dep, only needed here

    if output_path is None:
        output_path = f"/tmp/em-region-{int(time.time() * 1000)}.png"
    data = device.exec_out(["screencap", "-p"])
    with Image.open(io.BytesIO(data)) as im:
        x1, y1, x2, y2 = bounds
        crop = im.crop((x1, y1, x2, y2))
        crop.save(output_path)
        w, h = crop.size
    return {"path": output_path, "width": w, "height": h}
