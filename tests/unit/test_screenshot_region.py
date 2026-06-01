"""capture_region: 裁剪指定 bounds。"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from mobilecli.core import screenshot


class _FakeDevice:
    """exec_out 返回一张 100x200 的纯色 PNG。"""

    def exec_out(self, argv, timeout_s=30):
        img = Image.new("RGB", (100, 200), (10, 20, 30))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def test_capture_region_crops_bounds(tmp_path):
    out = tmp_path / "crop.png"
    res = screenshot.capture_region(_FakeDevice(), (10, 20, 60, 120), str(out))
    assert res["width"] == 50
    assert res["height"] == 100
    with Image.open(out) as im:
        assert im.size == (50, 100)
