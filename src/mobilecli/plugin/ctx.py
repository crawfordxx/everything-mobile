"""ExecContext -- the only surface plugin authors interact with.

Plugins MUST go through ExecContext methods. No direct subprocess, no direct
adb shell, no `_raw` access. This is what makes Layer 2.5 humanization +
governor + linter unbypassable from plugin code.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import app as core_app
from mobilecli.core import input as core_input
from mobilecli.core import media as core_media
from mobilecli.core import screenshot as core_screenshot
from mobilecli.core import ui as core_ui
from mobilecli.safety import humanize as _hz
from mobilecli.safety.governor import SessionGovernor
from mobilecli.safety.linter import ContentLinter


def _pace_enabled() -> bool:
    return os.environ.get("EM_PACE", "1") != "0"


def _pace_bounds() -> tuple[float, float]:
    try:
        lo = float(os.environ.get("EM_PACE_MIN", "2"))
        hi = float(os.environ.get("EM_PACE_MAX", "10"))
    except ValueError:
        return (2.0, 10.0)  # 非数字 env -> 回落默认,不让一个笔误炸掉整条 verb
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

    def reading_pause(self, text_length: int = 200) -> None:
        """模拟阅读停顿(浏览类 verb 读完内容后调)。"""
        if _pace_enabled():
            time.sleep(_hz.read_pause_s(text_length=text_length))

    def idle_browse(self, prob: float = 0.4) -> None:
        """偶发(prob 概率)小幅来回滑动模拟看内容。

        故意走 self.swipe(而非直接 swipe_humanized):这条 wobble 也应带上
        操作间 pace 延迟——人看内容时的小动作本就有停顿,慢=像人。
        """
        if not _pace_enabled() or random.random() > prob:
            return
        sh = 2410
        start, end = _hz.micro_wobble_swipe(center_y=sh // 2, screen_h=sh)
        self.swipe(start, end)

    def tap_node(self, node: dict[str, Any]) -> dict[str, Any]:
        self._pace()
        bounds = node.get("bounds")
        if not bounds:
            raise ValueError(f"node has no bounds: {node!r}")
        bx1, by1, bx2, by2 = bounds[0], bounds[1], bounds[2], bounds[3]
        return core_input.tap_humanized(self.device, bounds=(bx1, by1, bx2, by2))

    def tap_xy(self, x: int, y: int) -> dict[str, Any]:
        self._pace()
        return core_input.tap_humanized(self.device, x=x, y=y)

    def swipe(self, start: tuple[int, int], end: tuple[int, int]) -> dict[str, Any]:
        self._pace()
        return core_input.swipe_humanized(self.device, start, end)

    def swipe_feed(self, direction: str = "up") -> dict[str, Any]:
        """Feed 上下滑一屏(模拟人为刷视频):横向位置/纵深每次随机。

        up = 手指上滑(看下一条);down = 手指下滑(回看上一条)。实际手势经
        swipe(人性化:操作间 pace + 端点抖动 + 随机时长)发出。
        """
        w, h = core_input.screen_wh(self.device)
        x1 = int(w * random.uniform(0.40, 0.60))
        x2 = x1 + random.randint(-40, 40)
        if direction == "down":
            y1 = int(h * random.uniform(0.28, 0.38))
            y2 = int(h * random.uniform(0.62, 0.75))
        else:
            y1 = int(h * random.uniform(0.62, 0.75))
            y2 = int(h * random.uniform(0.25, 0.38))
        return {**self.swipe((x1, y1), (x2, y2)), "direction": direction}

    def type_text(self, text: str) -> dict[str, Any]:
        self._pace()
        return core_input.type_text_humanized(self.device, text)

    def keyevent(self, code: int | str) -> dict[str, Any]:
        self._pace()
        return core_input.keyevent_raw(self.device, code)


@dataclass
class UiModule:
    device: Device

    def dump(self, output_path: str | None = None) -> dict[str, Any]:
        return core_ui.dump(self.device, output_path)

    def find_by_resource_id(self, xml: str, rid: str) -> dict[str, Any] | None:
        return core_ui.find_by_resource_id(xml, rid)

    def find_by_content_desc(self, xml: str, desc: str) -> dict[str, Any] | None:
        return core_ui.find_by_content_desc(xml, desc)

    def find_by_text(self, xml: str, text: str) -> dict[str, Any] | None:
        return core_ui.find_by_text(xml, text)

    def find_all_by_resource_id(self, xml: str, rid: str) -> list[dict[str, Any]]:
        return core_ui.find_all_by_resource_id(xml, rid)

    def screenshot(self, output_path: str | None = None) -> dict[str, Any]:
        return core_screenshot.capture(self.device, output_path)

    def screenshot_region(
        self, bounds: tuple[int, int, int, int], output_path: str | None = None
    ) -> dict[str, Any]:
        return core_screenshot.capture_region(self.device, bounds, output_path)


@dataclass
class MediaModule:
    device: Device

    def push_to_gallery(self, local_paths: list[str], subdir: str = "em-publish") -> dict[str, Any]:
        return core_media.push_to_gallery(self.device, local_paths, subdir)


@dataclass
class AppModule:
    device: Device
    package: str

    def launch(self) -> dict[str, Any]:
        return core_app.launch(self.device, self.package)

    def force_stop(self) -> dict[str, Any]:
        """Kill all of the app's processes; next launch starts from a clean task."""
        return core_app.force_stop(self.device, self.package)

    def foreground(self) -> dict[str, Any]:
        return core_app.foreground(self.device)

    def ensure_foreground(self) -> dict[str, Any]:
        fg = self.foreground()
        if fg.get("package") != self.package:
            return self.launch()
        return fg


@dataclass
class ExecContext:
    device: Device
    input: InputModule
    ui: UiModule
    app: AppModule
    media: MediaModule
    governor: SessionGovernor
    linter: ContentLinter

    @classmethod
    def build(
        cls,
        device: Device,
        package: str,
        account: str,
        caps: dict[str, int],
        extra_lint: list[str],
    ) -> ExecContext:
        return cls(
            device=device,
            input=InputModule(device=device),
            ui=UiModule(device=device),
            app=AppModule(device=device, package=package),
            media=MediaModule(device=device),
            governor=SessionGovernor(account=account, caps=caps),
            linter=ContentLinter(extra_patterns=extra_lint),
        )
