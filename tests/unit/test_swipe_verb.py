"""douyin / kuaishou swipe verb:模拟人为上下滑动 feed。

几何约定:up = 手指上滑(看下一条),起点在屏幕下半部、终点在上半部;down 反之。
横向位置/纵深每次随机,实际手势经 swipe_humanized(随机时长+端点抖动)发出。
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field

import pytest

from mobilecli.apps._feed import run_swipe
from mobilecli.apps.douyin import app as douyin_app
from mobilecli.apps.kuaishou import app as kuaishou_app
from mobilecli.envelope import EmError, ErrorCode
from mobilecli.plugin.ctx import InputModule

_SWIPE_RE = re.compile(r"input swipe (\d+) (\d+) (\d+) (\d+) (\d+)")


@dataclass
class _FakeDevice:
    cmds: list[str] = field(default_factory=list)

    def shell(self, cmd: str, timeout_s: int = 30) -> str:
        self.cmds.append(cmd)
        if cmd == "wm size":
            return "Physical size: 1080x2400"
        return ""


def _last_swipe(dev: _FakeDevice) -> tuple[int, int, int, int, int]:
    for cmd in reversed(dev.cmds):
        m = _SWIPE_RE.match(cmd)
        if m:
            return tuple(int(g) for g in m.groups())  # type: ignore[return-value]
    raise AssertionError(f"no input swipe issued: {dev.cmds}")


@pytest.fixture
def no_pace(monkeypatch):
    monkeypatch.setenv("EM_PACE", "0")
    monkeypatch.delenv("EM_CURVED_SWIPE", raising=False)


@pytest.mark.parametrize("app", [douyin_app, kuaishou_app])
def test_swipe_registered_without_commit_gate(app):
    assert "swipe" in app.verbs
    assert app.verbs["swipe"].requires_commit_flag is False


@pytest.mark.parametrize("app", [douyin_app, kuaishou_app])
def test_swipe_arg_defaults(app):
    p = argparse.ArgumentParser()
    assert app.verbs["swipe"].add_args is not None
    app.verbs["swipe"].add_args(p)
    ns = p.parse_args([])
    assert ns.direction == "up"
    assert ns.times == 1


def test_swipe_feed_up_goes_bottom_to_top(no_pace):
    dev = _FakeDevice()
    InputModule(device=dev).swipe_feed("up")  # type: ignore[arg-type]
    x1, y1, x2, y2, dur = _last_swipe(dev)
    assert y1 > y2, "up 滑应从下往上"
    assert 0.5 * 2400 < y1 < 0.85 * 2400
    assert 0.15 * 2400 < y2 < 0.5 * 2400
    assert 0.3 * 1080 < x1 < 0.7 * 1080
    assert dur > 0


def test_swipe_feed_down_goes_top_to_bottom(no_pace):
    dev = _FakeDevice()
    InputModule(device=dev).swipe_feed("down")  # type: ignore[arg-type]
    _, y1, _, y2, _ = _last_swipe(dev)
    assert y1 < y2, "down 滑应从上往下"


def test_run_swipe_repeats_times(no_pace):
    dev = _FakeDevice()

    @dataclass
    class _FakeApp:
        def foreground(self):
            return {"package": "p", "activity": "a"}

    @dataclass
    class _Ctx:
        input: InputModule
        app: _FakeApp

    ctx = _Ctx(input=InputModule(device=dev), app=_FakeApp())  # type: ignore[arg-type]
    res = run_swipe(argparse.Namespace(direction="up", times=3), ctx)  # type: ignore[arg-type]
    assert res["times"] == 3
    assert len(res["moves"]) == 3
    assert len([c for c in dev.cmds if c.startswith("input swipe")]) == 3


def test_run_swipe_rejects_absurd_times(no_pace):
    ctx = argparse.Namespace(input=None, app=None)
    with pytest.raises(EmError) as exc:
        run_swipe(argparse.Namespace(direction="up", times=0), ctx)  # type: ignore[arg-type]
    assert exc.value.code is ErrorCode.INVALID_ARG
    with pytest.raises(EmError):
        run_swipe(argparse.Namespace(direction="up", times=99), ctx)  # type: ignore[arg-type]
