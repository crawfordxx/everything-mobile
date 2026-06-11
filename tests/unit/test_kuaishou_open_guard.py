"""kuaishou open 的落点前置校验。

`open --cx/--cy` 按 search 返回的坐标盲点。真机复现:若点击时页面已退回首页
(弹窗/超时很常见),search 返回的底部坐标 (≈540,≈2283) 正好砸中首页底部导航
中央的「拍摄」按钮 → 误开相机(CameraActivity)。修复:tap 前必须在
SearchActivity,否则拒绝并报 APP_NOT_FOREGROUND。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any

import pytest

from mobilecli.apps.kuaishou import open_result
from mobilecli.envelope import EmError, ErrorCode


@dataclass
class _FakeInput:
    taps: list[tuple[int, int]] = field(default_factory=list)

    def tap_xy(self, x: int, y: int) -> dict[str, Any]:
        self.taps.append((x, y))
        return {"x": x, "y": y}

    def tap_node(self, node: dict[str, Any]) -> dict[str, Any]:
        self.taps.append((node["cx"], node["cy"]))
        return {"x": node["cx"], "y": node["cy"]}

    def keyevent(self, code: int | str) -> dict[str, Any]:
        return {"code": str(code)}

    def idle_browse(self) -> None:
        pass


@dataclass
class _FakeApp:
    activity: str

    def foreground(self) -> dict[str, Any]:
        return {"package": "com.smile.gifmaker", "activity": self.activity}


@dataclass
class _FakeCtx:
    input: _FakeInput
    app: _FakeApp


def test_open_refuses_blind_tap_when_not_on_search_page():
    """页面在首页时 open 必须拒绝盲点坐标 —— (540,2283) 在首页就是「拍摄」按钮。"""
    ctx = _FakeCtx(input=_FakeInput(), app=_FakeApp("com.yxcorp.gifshow.HomeActivity"))
    args = argparse.Namespace(cx=540, cy=2283, rank=None)
    with pytest.raises(EmError) as exc:
        open_result(args, ctx)  # type: ignore[arg-type]
    assert exc.value.code is ErrorCode.APP_NOT_FOREGROUND
    assert ctx.input.taps == []  # 关键:一次点击都不能发


def test_open_refuses_when_on_camera_page():
    ctx = _FakeCtx(
        input=_FakeInput(),
        app=_FakeApp("com.yxcorp.gifshow.camera.record.CameraActivity"),
    )
    args = argparse.Namespace(cx=540, cy=1200, rank=None)
    with pytest.raises(EmError) as exc:
        open_result(args, ctx)  # type: ignore[arg-type]
    assert exc.value.code is ErrorCode.APP_NOT_FOREGROUND
    assert ctx.input.taps == []
