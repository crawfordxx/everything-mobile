"""App lifecycle helpers."""

from __future__ import annotations

import re
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.envelope import EmError, ErrorCode

# Android package names: alnum + dot + underscore. Strict to prevent shell injection
# through Device.shell() which passes a single string to `adb shell`.
_PACKAGE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$")


def _validate_package(package: str) -> None:
    if not _PACKAGE_RE.match(package):
        raise EmError(
            ErrorCode.UNKNOWN,
            f"invalid package name: {package!r}",
            hint="package must match ^[a-zA-Z][a-zA-Z0-9_]*(\\.[a-zA-Z0-9_]+)+$",
        )


def is_installed(device: Device, package: str) -> bool:
    _validate_package(package)
    out = device.shell(f"pm list packages {package}")
    return any(line.strip() == f"package:{package}" for line in out.splitlines())


def launch(device: Device, package: str) -> dict[str, Any]:
    _validate_package(package)
    if not is_installed(device, package):
        raise EmError(
            ErrorCode.APP_NOT_INSTALLED,
            f"{package} not installed",
            hint="run `pm list packages | grep` to confirm",
        )
    device.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")
    return {"package": package}


def force_stop(device: Device, package: str) -> dict[str, Any]:
    """Kill all processes belonging to `package` so the next launch starts fresh.

    Stronger than `back` + relaunch -- this clears the task stack, so the app
    cannot be brought back into a half-state (e.g. DetailActivity on top from
    a previous session). Used as a fallback in plugins when the back-press
    recovery loop fails to reach the home screen.
    """
    _validate_package(package)
    device.shell(f"am force-stop {package}")
    return {"package": package, "killed": True}


_TOP_RESUMED_RE = re.compile(r"topResumedActivity=ActivityRecord\{[^}]*?\s([^\s/}]+)/([^\s}]+)")
_FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*\s([^/\s]+)/([^\s}]+)")


def parse_top_resumed(out: str) -> dict[str, Any] | None:
    """`dumpsys activity activities` 里的 topResumedActivity -> {package, activity}。"""
    m = _TOP_RESUMED_RE.search(out)
    if not m:
        return None
    return {"package": m.group(1), "activity": m.group(2)}


def parse_current_focus(out: str) -> dict[str, Any] | None:
    """`dumpsys window` 里的 mCurrentFocus -> {package, activity};非 activity 窗口返回 None。"""
    m = _FOCUS_RE.search(out)
    if not m:
        return None
    return {"package": m.group(1), "activity": m.group(2)}


def foreground(device: Device) -> dict[str, Any]:
    """当前前台 activity。

    优先 topResumedActivity(当前 resumed 的页面);mCurrentFocus 是「焦点窗口」,
    弹窗/输入法/toast 占焦点时 ≠ 当前页面 —— 曾导致 kuaishou _on_home 在已回首页
    时仍判 False,连按 BACK + force-stop(把 app 退出、底下的任务浮上来)。仅当
    activity dump 不可用时才回退焦点窗口。
    """
    try:
        fg = parse_top_resumed(device.shell("dumpsys activity activities"))
        if fg is not None:
            return fg
    except EmError:
        pass
    return parse_current_focus(device.shell("dumpsys window")) or {"package": "", "activity": ""}


def install(device: Device, apk_path: str) -> dict[str, Any]:
    """Install APK via Layer 1's Device.install_apk()."""
    device.install_apk(apk_path)
    return {"apk": apk_path, "result": "success"}
