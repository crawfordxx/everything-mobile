"""ExecContext -- the only surface plugin authors interact with.

Plugins MUST go through ExecContext methods. No direct subprocess, no direct
adb shell, no `_raw` access. This is what makes Layer 2.5 humanization +
governor + linter unbypassable from plugin code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import app as core_app
from mobilecli.core import input as core_input
from mobilecli.core import screenshot as core_screenshot
from mobilecli.core import ui as core_ui
from mobilecli.safety.governor import SessionGovernor
from mobilecli.safety.linter import ContentLinter


@dataclass
class InputModule:
    device: Device

    def tap_node(self, node: dict[str, Any]) -> dict[str, Any]:
        bounds = node.get("bounds")
        if not bounds:
            raise ValueError(f"node has no bounds: {node!r}")
        bx1, by1, bx2, by2 = bounds[0], bounds[1], bounds[2], bounds[3]
        return core_input.tap_humanized(self.device, bounds=(bx1, by1, bx2, by2))

    def tap_xy(self, x: int, y: int) -> dict[str, Any]:
        return core_input.tap_humanized(self.device, x=x, y=y)

    def swipe(self, start: tuple[int, int], end: tuple[int, int]) -> dict[str, Any]:
        return core_input.swipe_humanized(self.device, start, end)

    def type_text(self, text: str) -> dict[str, Any]:
        return core_input.type_text_humanized(self.device, text)

    def keyevent(self, code: int | str) -> dict[str, Any]:
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
            governor=SessionGovernor(account=account, caps=caps),
            linter=ContentLinter(extra_patterns=extra_lint),
        )
