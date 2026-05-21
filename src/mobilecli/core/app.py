"""App lifecycle helpers."""

from __future__ import annotations

import re
import subprocess
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.envelope import EmError, ErrorCode


def is_installed(device: Device, package: str) -> bool:
    out = device.shell(f"pm list packages {package}")
    return any(line.strip() == f"package:{package}" for line in out.splitlines())


def launch(device: Device, package: str) -> dict[str, Any]:
    if not is_installed(device, package):
        raise EmError(
            ErrorCode.APP_NOT_INSTALLED,
            f"{package} not installed",
            hint="run `pm list packages | grep` to confirm",
        )
    device.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")
    return {"package": package}


_FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*\s([^/\s]+)/([^\s}]+)")


def foreground(device: Device) -> dict[str, Any]:
    out = device.shell("dumpsys window")
    m = _FOCUS_RE.search(out)
    if not m:
        return {"package": "", "activity": ""}
    return {"package": m.group(1), "activity": m.group(2)}


def install(device: Device, apk_path: str) -> dict[str, Any]:
    """`adb install -r <apk>` -- uses subprocess directly (not `adb shell`)."""
    proc = subprocess.run(
        ["adb", "-s", device.serial, "install", "-r", apk_path],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        raise EmError(ErrorCode.UNKNOWN, proc.stderr.strip() or "install failed")
    return {"apk": apk_path, "result": "success"}
