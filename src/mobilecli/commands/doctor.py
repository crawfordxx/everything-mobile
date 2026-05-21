"""`mobilecli doctor` -- environment self-check.

Returns {checks: [{name, status, detail}], summary: {pass, fail, warn}}.
"""

from __future__ import annotations

import argparse
import shutil
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import ime as core_ime
from mobilecli.envelope import envelope


def _check(name: str, status: str, detail: str = "") -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail}


def _summary(checks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "checks": checks,
        "summary": {
            "pass": sum(1 for c in checks if c["status"] == "pass"),
            "fail": sum(1 for c in checks if c["status"] == "fail"),
            "warn": sum(1 for c in checks if c["status"] == "warn"),
        },
    }


def add_parser(subparsers: Any) -> None:
    subparsers.add_parser("doctor", help="Environment self-check")


@envelope(command="doctor")
def _run(*, device: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    if shutil.which("adb"):
        checks.append(_check("adb_available", "pass"))
    else:
        checks.append(_check("adb_available", "fail", "install Android platform-tools"))
        return _summary(checks)

    try:
        dev = Device.from_serial(device or None)
        checks.append(_check("device_online", "pass", dev.serial))
    except Exception as e:  # noqa: BLE001
        checks.append(_check("device_online", "fail", str(e)))
        return _summary(checks)

    try:
        if core_ime.ADBKEYBOARD_ID in core_ime.list_imes(dev):
            checks.append(_check("adbkeyboard_installed", "pass"))
        else:
            checks.append(
                _check(
                    "adbkeyboard_installed",
                    "warn",
                    "install for Chinese input: https://github.com/senzhk/ADBKeyBoard",
                ),
            )
    except Exception as e:  # noqa: BLE001
        checks.append(_check("adbkeyboard_installed", "warn", str(e)))

    # Layer 2.5 humanization + fingerprint signals
    from mobilecli.safety import device_check
    from mobilecli.safety.governor import DEFAULT_STATE_DIR

    checks.extend(device_check.signals(dev))

    if DEFAULT_STATE_DIR.exists():
        checks.append(_check("session_state_dir", "pass", str(DEFAULT_STATE_DIR)))
    else:
        checks.append(
            _check(
                "session_state_dir",
                "warn",
                f"will be created on first verb: {DEFAULT_STATE_DIR}",
            ),
        )

    return _summary(checks)


def run(args: argparse.Namespace) -> str:
    return _run(device=args.serial or "")
