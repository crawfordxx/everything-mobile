"""kuaishou close-popup verb:通用关弹窗。

两类弹窗的对策:
- 可 dump 的静态弹窗:按 text/content-desc 命中已识别关闭控件(忽略/跳过/关闭/
  我知道了…),逐轮点掉;
- 动画促销弹窗(礼盒/视频广告持续动画 → uiautomator 取不到 idle,dump 直接失败):
  BACK 退一层再试,最多 3 次(与 search goal-driven 进页同款对策)。
只点已识别控件,绝不乱点空白(避免把广告点开)。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any

from mobilecli.apps.kuaishou import app as kuaishou_app
from mobilecli.apps.kuaishou import close_popup
from mobilecli.core import ui as core_ui
from mobilecli.envelope import EmError, ErrorCode

_POPUP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="我知道了" class="android.widget.TextView" clickable="true" bounds="[390,1500][690,1600]"/>
</hierarchy>"""

_CLEAN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="" content-desc="查找" class="android.widget.ImageView" clickable="true" bounds="[952,184][1057,289]"/>
</hierarchy>"""


@dataclass
class _FakeUi:
    """按脚本回放 dump:元素查找直接复用 core_ui 真实现。"""

    script: list[str | None]  # None = 本次 dump 失败(动画弹窗)
    tmp_path: Any = None
    calls: int = 0

    def dump(self) -> dict[str, Any]:
        item = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if item is None:
            raise EmError(ErrorCode.ADB_TIMEOUT, "uiautomator not idle (动画弹窗)")
        p = self.tmp_path / f"dump{self.calls}.xml"
        p.write_text(item, encoding="utf-8")
        return {"path": str(p)}

    def find_by_text(self, xml: str, text: str) -> dict[str, Any] | None:
        return core_ui.find_by_text(xml, text)

    def find_by_content_desc(self, xml: str, desc: str) -> dict[str, Any] | None:
        return core_ui.find_by_content_desc(xml, desc)


@dataclass
class _FakeInput:
    taps: list[dict[str, Any]] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)

    def tap_node(self, node: dict[str, Any]) -> dict[str, Any]:
        self.taps.append(node)
        return {"x": node["cx"], "y": node["cy"]}

    def keyevent(self, code: int | str) -> dict[str, Any]:
        self.keys.append(str(code))
        return {"code": str(code)}


@dataclass
class _FakeDevice:
    def shell(self, cmd: str, timeout_s: int = 30) -> str:
        return ""


@dataclass
class _FakeApp:
    def foreground(self) -> dict[str, Any]:
        return {"package": "com.smile.gifmaker", "activity": "com.yxcorp.gifshow.HomeActivity"}


@dataclass
class _FakeCtx:
    ui: _FakeUi
    input: _FakeInput
    device: _FakeDevice
    app: _FakeApp


def _ctx(tmp_path, script) -> _FakeCtx:
    return _FakeCtx(
        ui=_FakeUi(script=script, tmp_path=tmp_path),
        input=_FakeInput(),
        device=_FakeDevice(),
        app=_FakeApp(),
    )


def test_close_popup_registered_without_commit_gate():
    assert "close-popup" in kuaishou_app.verbs
    assert kuaishou_app.verbs["close-popup"].requires_commit_flag is False


def test_close_popup_taps_known_close_label(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    ctx = _ctx(tmp_path, [_POPUP_XML, _CLEAN_XML])
    res = close_popup(argparse.Namespace(), ctx)  # type: ignore[arg-type]
    assert res["dismissed"] == ["我知道了"]
    assert len(ctx.input.taps) == 1
    assert ctx.input.keys == []  # 静态弹窗不需要 BACK


def test_close_popup_backs_through_animated_popup(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    # 前两次 dump 失败(动画弹窗) → BACK ×2;第三次干净 → 结束
    ctx = _ctx(tmp_path, [None, None, _CLEAN_XML])
    res = close_popup(argparse.Namespace(), ctx)  # type: ignore[arg-type]
    assert res["dismissed"] == []
    assert res["backs"] == 2
    assert ctx.input.keys == ["back", "back"]
    assert ctx.input.taps == []  # 绝不乱点


def test_close_popup_back_budget_capped(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    # dump 一直失败:BACK 最多 3 次后放弃,不无限循环
    ctx = _ctx(tmp_path, [None])
    res = close_popup(argparse.Namespace(), ctx)  # type: ignore[arg-type]
    assert res["backs"] == 3
    assert ctx.input.keys == ["back", "back", "back"]


def test_close_popup_noop_on_clean_page(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    ctx = _ctx(tmp_path, [_CLEAN_XML])
    res = close_popup(argparse.Namespace(), ctx)  # type: ignore[arg-type]
    assert res["dismissed"] == []
    assert ctx.input.taps == []
    assert ctx.input.keys == []
