# 风控增强 Implementation Plan(操作间高斯延迟 + sendevent 曲线滑动 + 阅读行为)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** 把已有但未接入的人类化能力真正接进 `ctx.input.*`,补封控三短板:操作间高斯延迟(默认 2~10s,可配)、sendevent 连续曲线滑动(0.8~2.0s,失败回退直线)、阅读停顿/小幅来回滑动。

**Architecture:** 见 `docs/superpowers/specs/2026-06-01-fengkong-humanize-enhance-design.md`。纯采样器 + 解析器走单测;pacing 在 `InputModule` 单一钩子;曲线滑动 `core/touch.py`(运行时探测设备 + sendevent 单命令 + 回退)。决策已定:pacing 默认开 2~10s 可环境变量调/关;曲线走 sendevent + 回退。

**Tech Stack:** Python 3.10+, pytest, adb(getevent/sendevent/input)。

**真机事实:** 触摸设备 `/dev/input/event1`,X∈[0,12799] Y∈[0,28559],屏 1080×2410(运行时探测,勿硬编码)。fixture:`tests/fixtures/getevent-touch.txt`。

---

## Task 1: humanize 采样器(纯函数)

**Files:** Modify `src/mobilecli/safety/humanize.py`; Test `tests/unit/test_humanize_pace.py`

- [ ] Step 1: 写测试 `tests/unit/test_humanize_pace.py`:
```python
from __future__ import annotations
from mobilecli.safety import humanize as hz


def test_pace_delay_in_range():
    xs = [hz.pace_delay_s(2.0, 10.0) for _ in range(2000)]
    assert all(2.0 <= x <= 10.0 for x in xs)
    assert 5.0 < sum(xs) / len(xs) < 7.0  # 均值≈6


def test_swipe_duration_range():
    xs = [hz.swipe_duration_s() for _ in range(500)]
    assert all(0.8 <= x <= 2.0 for x in xs)


def test_micro_wobble_returns_two_points():
    start, end = hz.micro_wobble_swipe(center_y=1200, screen_h=2410)
    assert len(start) == 2 and len(end) == 2
    assert start[0] == end[0]  # 垂直来回,x 不变
    assert start != end
```
- [ ] Step 2: 跑 → FAIL(无 `pace_delay_s`)。
- [ ] Step 3: 在 `humanize.py` 末尾加:
```python
def pace_delay_s(lo: float = 2.0, hi: float = 10.0) -> float:
    """操作间延迟:截断高斯,均值=(lo+hi)/2,σ=(hi-lo)/4,clamp[lo,hi]。"""
    mu = (lo + hi) / 2.0
    sigma = (hi - lo) / 4.0
    return max(lo, min(hi, random.gauss(mu, sigma)))


def swipe_duration_s(lo: float = 0.8, hi: float = 2.0) -> float:
    return random.uniform(lo, hi)


def micro_wobble_swipe(center_y: int, screen_h: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """阅读时小幅来回:在屏幕水平中线、center_y 附近做一段短垂直滑动(看内容)。"""
    cx = 540  # 近似屏中线(1080 宽);调用方按需可忽略
    amp = random.randint(int(screen_h * 0.04), int(screen_h * 0.10))
    direction = random.choice((-1, 1))
    y0 = max(amp + 1, min(screen_h - amp - 1, center_y))
    return (cx, y0), (cx, y0 + direction * amp)
```
- [ ] Step 4: 跑 → 3 PASS。全套 → green。
- [ ] Step 5: Commit `feat(humanize): pace_delay_s/swipe_duration_s/micro_wobble_swipe samplers`

## Task 2: 设备探测 probe_touch_device(纯解析 + 缓存)

**Files:** Create `src/mobilecli/core/touch.py`; Test `tests/unit/test_touch_probe.py`

- [ ] Step 1: 写测试 `tests/unit/test_touch_probe.py`:
```python
from __future__ import annotations
from pathlib import Path
from mobilecli.core import touch

FIX = Path(__file__).parent.parent / "fixtures"


def test_parse_getevent_picks_touch_device():
    out = (FIX / "getevent-touch.txt").read_text()
    info = touch.parse_getevent(out)
    assert info == {"event_node": "/dev/input/event1", "x_max": 12799, "y_max": 28559}


def test_parse_getevent_none_when_no_touch():
    info = touch.parse_getevent("add device 1: /dev/input/event0\n  name: \"gpio_keys\"\n")
    assert info is None
```
- [ ] Step 2: 跑 → FAIL。
- [ ] Step 3: 创建 `src/mobilecli/core/touch.py`:
```python
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
```
- [ ] Step 4: 跑 → 2 PASS。Commit `feat(core/touch): probe_touch_device + getevent parser`

## Task 3: 曲线滑动 curved_swipe(sendevent 单命令)

**Files:** Modify `src/mobilecli/core/touch.py`; Test `tests/unit/test_touch_curved.py`

- [ ] Step 1: 写测试 `tests/unit/test_touch_curved.py`:
```python
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
    assert len(dev.cmds) == 1                      # 单条 shell
    cmd = dev.cmds[0]
    assert cmd.count("sendevent /dev/input/event1") >= 3 * len(pts)  # 至少每点 X/Y/SYN
    assert "330 1" in cmd and "330 0" in cmd        # BTN_TOUCH down/up
    assert "sleep" in cmd
    # X 缩放: 100/1080*12800 ≈ 1185
    assert "53 1185" in cmd or "53 1184" in cmd


def test_curved_swipe_none_without_touch_info():
    dev = _FakeDevice()
    res = touch.curved_swipe(dev, [(1, 2), (3, 4)], 1.0, (1080, 2410), touch_info=None)
    assert res is None
    assert dev.cmds == []
```
- [ ] Step 2: 跑 → FAIL。
- [ ] Step 3: 在 `touch.py` 加(event 码常量 + 函数):
```python
# evdev numeric codes
_EV_SYN, _EV_KEY, _EV_ABS = 0, 1, 3
_SYN_REPORT = 0
_BTN_TOUCH, _BTN_TOOL_FINGER = 330, 325
_ABS_MT_SLOT, _ABS_MT_TRACKING_ID = 47, 57
_ABS_MT_POSITION_X, _ABS_MT_POSITION_Y = 53, 54
_TRACKING_ID = 4242


def curved_swipe(device, points, duration_s, screen_wh, touch_info):
    """沿 points(屏幕坐标)发一条连续 type-B 多点手势(单条 adb shell sendevent 序列)。
    touch_info=None -> 返回 None(回退)。"""
    if not touch_info or len(points) < 2:
        return None
    node = touch_info["event_node"]
    xmax, ymax = touch_info["x_max"], touch_info["y_max"]
    sw, sh = screen_wh

    def sx(x): return max(0, min(xmax, round(x * (xmax + 1) / sw)))
    def sy(y): return max(0, min(ymax, round(y * (ymax + 1) / sh)))

    def se(t, c, v): return f"sendevent {node} {t} {c} {v}"

    dt = max(0.005, duration_s / len(points))
    parts: list[str] = []
    x0, y0 = points[0]
    parts += [
        se(_EV_ABS, _ABS_MT_SLOT, 0),
        se(_EV_ABS, _ABS_MT_TRACKING_ID, _TRACKING_ID),
        se(_EV_KEY, _BTN_TOUCH, 1),
        se(_EV_KEY, _BTN_TOOL_FINGER, 1),
        se(_EV_ABS, _ABS_MT_POSITION_X, sx(x0)),
        se(_EV_ABS, _ABS_MT_POSITION_Y, sy(y0)),
        se(_EV_SYN, _SYN_REPORT, 0),
        f"sleep {dt:.3f}",
    ]
    for (x, y) in points[1:]:
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
    device.shell(cmd, timeout_s=max(10, int(duration_s) + 8))
    return {"event_node": node, "points": len(points), "duration_s": duration_s}
```
- [ ] Step 4: 跑 → 2 PASS(若缩放断言差 1,放宽到 `53 118` 前缀匹配)。Commit `feat(core/touch): curved_swipe via single sendevent command`

## Task 4: pacing 接入 InputModule + 曲线滑动接入 swipe_humanized

**Files:** Modify `src/mobilecli/plugin/ctx.py`(InputModule);`src/mobilecli/core/input.py`(swipe_humanized);Test `tests/unit/test_pacing.py`

- [ ] Step 1: 写测试 `tests/unit/test_pacing.py`:
```python
from __future__ import annotations
import mobilecli.plugin.ctx as ctxmod


class _Dev:
    def shell(self, *a, **k): return ""
    def exec_out(self, *a, **k): return b""


def test_pacing_disabled_via_env(monkeypatch):
    monkeypatch.setenv("EM_PACE", "0")
    slept = []
    monkeypatch.setattr(ctxmod.time, "sleep", lambda s: slept.append(s))
    im = ctxmod.InputModule(device=_Dev())
    im.keyevent("back"); im.keyevent("back")
    assert slept == []


def test_pacing_skips_first_then_paces(monkeypatch):
    monkeypatch.setenv("EM_PACE", "1")
    monkeypatch.setenv("EM_PACE_MIN", "2"); monkeypatch.setenv("EM_PACE_MAX", "10")
    slept = []
    monkeypatch.setattr(ctxmod.time, "sleep", lambda s: slept.append(s))
    im = ctxmod.InputModule(device=_Dev())
    im.keyevent("back")  # 首个不等
    im.keyevent("back")  # 第二个等
    assert len(slept) == 1 and 2.0 <= slept[0] <= 10.0
```
- [ ] Step 2: 跑 → FAIL。
- [ ] Step 3: `ctx.py` 顶部加 `import os` + `import time`(若缺);InputModule 改:
```python
def _pace_enabled() -> bool:
    return os.environ.get("EM_PACE", "1") != "0"

def _pace_bounds() -> tuple[float, float]:
    lo = float(os.environ.get("EM_PACE_MIN", "2"))
    hi = float(os.environ.get("EM_PACE_MAX", "10"))
    return (lo, hi) if hi > lo else (2.0, 10.0)


@dataclass
class InputModule:
    device: Device
    _first: bool = True

    def _pace(self) -> None:
        if not _pace_enabled():
            return
        if self._first:
            self._first = False
            return
        time.sleep(_hz.pace_delay_s(*_pace_bounds()))
    # 每个方法体首行 self._pace();swipe 见 Step 4
```
  在 `tap_node`/`tap_xy`/`type_text`/`keyevent` 首行加 `self._pace()`;import `from mobilecli.safety import humanize as _hz`。
- [ ] Step 4: `swipe` 方法接曲线:`self._pace()` 后调 `core_input.swipe_humanized(...)`(下面让 swipe_humanized 内部走曲线+回退)。改 `core/input.py` 的 `swipe_humanized`:
```python
def swipe_humanized(device, start, end):
    from mobilecli.core import touch as _touch
    from mobilecli.safety import humanize as _hz
    pts = _hz.bezier_swipe_points(start, end, n_points=24)
    dur = _hz.swipe_duration_s()  # 0.8~2.0s
    info = _touch.probe_touch_device(device)  # 可加简单缓存
    if info is not None:
        res = _touch.curved_swipe(device, pts, dur, _screen_wh(device), info)
        if res is not None:
            return {"mode": "curved", **res}
    # 回退:直线 input swipe(duration 0.8~2.0s)
    sx, sy = _hz.jittered_xy(start[0], start[1], radius=4)
    ex, ey = _hz.jittered_xy(end[0], end[1], radius=4)
    device.shell(f"input swipe {sx} {sy} {ex} {ey} {int(dur*1000)}")
    return {"mode": "line", "x1": sx, "y1": sy, "x2": ex, "y2": ey, "duration_ms": int(dur*1000)}
```
  `_screen_wh(device)`:`wm size` 解析(`Physical size: 1080x2410`),失败默认 (1080,2410)。加该 helper。
- [ ] Step 5: 跑 `test_pacing.py` + 全套 → green。Commit `feat(input): pacing in InputModule + curved swipe with line fallback`

## Task 5: 阅读行为接入浏览 verb

**Files:** Modify `src/mobilecli/plugin/ctx.py`(InputModule 加 reading_pause/idle_browse);各 app `open`/`detail` 接入

- [ ] Step 1: InputModule 加:
```python
    def reading_pause(self, text_length: int = 200) -> None:
        if _pace_enabled():
            time.sleep(_hz.read_pause_s(text_length=text_length))

    def idle_browse(self, prob: float = 0.4) -> None:
        """偶发小幅来回滑动模拟看内容(prob 概率触发一次 wobble)。"""
        if not _pace_enabled() or random.random() > prob:
            return
        sw, sh = 1080, 2410
        start, end = _hz.micro_wobble_swipe(center_y=sh // 2, screen_h=sh)
        self.swipe(start, end)
        time.sleep(_hz.read_pause_s(seen_recently=True))
```
  (import `random`;reading_pause/idle_browse 自身不调 `_pace`,避免双重延迟。)
- [ ] Step 2: 在 douyin/xiaohongshu/kuaishou 的 `open`/`detail` verb 读取数据后,加 `ctx.input.reading_pause()`,`open` 末尾偶发 `ctx.input.idle_browse()`。**只接浏览语义,不接 publish/profile 填表流程。**
- [ ] Step 3: 全套单测 green(这些是行为增强,无新单测;确保不破坏现有)。Commit `feat(apps): reading pause + idle browse on open/detail (browse verbs)`

## Task 6: 集成验证(真机,控制者跑)

- [ ] sendevent 曲线:真机 probe 成功 → 一条命令真实滚动 feed;对比直线观感;时长 0.8~2.0s。
- [ ] pacing:跑一个 verb 看动作间隔变长;`EM_PACE=0` 恢复快。
- [ ] 回退:模拟 probe 失败仍能滑动。
- [ ] **回归**:`EM_PACE=0` 跑一遍 publish dry-run + 三端 profile,确保功能未被 pacing/曲线破坏。

## Task 7: 文档

- [ ] README「人类化与风控约束」小节补:操作间高斯延迟(EM_PACE/EM_PACE_MIN/MAX)、sendevent 曲线滑动+回退、阅读行为。
- [ ] `docs/anti-risk-control.md` 标注这些已从"参数"变为"已实现接入"。
- [ ] Commit `docs: 风控增强(pacing/曲线/阅读)README + anti-risk 标注`

## Self-Review notes
- spec §6 七阶段全覆盖(Task1-7)。pacing 默认开可配(决策);曲线 sendevent+回退(决策)。
- 命名一致:`pace_delay_s`/`swipe_duration_s`/`micro_wobble_swipe`、`parse_getevent`/`probe_touch_device`/`curved_swipe`、`_pace`/`_pace_enabled`/`_pace_bounds`。
- 永不退化:曲线探测失败回退直线(Task4 Step4);pacing 可 `EM_PACE=0` 关。
- 真机部分(曲线滚动 / 回归)控制者跑,subagent 只写代码+单测。
