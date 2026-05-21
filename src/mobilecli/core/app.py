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


_FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*\s([^/\s]+)/([^\s}]+)")


def foreground(device: Device) -> dict[str, Any]:
    out = device.shell("dumpsys window")
    m = _FOCUS_RE.search(out)
    if not m:
        return {"package": "", "activity": ""}
    return {"package": m.group(1), "activity": m.group(2)}


def install(device: Device, apk_path: str) -> dict[str, Any]:
    """Install APK via Layer 1's Device.install_apk()."""
    device.install_apk(apk_path)
    return {"apk": apk_path, "result": "success"}
