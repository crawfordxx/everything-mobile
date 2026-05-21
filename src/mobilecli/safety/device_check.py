"""Device fingerprint checks -- what platforms might detect."""

from __future__ import annotations

from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import ime as core_ime


def signals(device: Device) -> list[dict[str, Any]]:
    """Return a list of fingerprint signals with status (pass/warn/fail)."""
    checks: list[dict[str, Any]] = []

    try:
        current = core_ime.current_ime(device)
        if current == core_ime.ADBKEYBOARD_ID:
            checks.append(
                {
                    "name": "ime_not_adbkeyboard_default",
                    "status": "warn",
                    "detail": "ADBKeyboard is the active IME -- risky if not transient",
                }
            )
        else:
            checks.append({"name": "ime_not_adbkeyboard_default", "status": "pass"})
    except Exception as e:  # noqa: BLE001
        checks.append(
            {"name": "ime_not_adbkeyboard_default", "status": "warn", "detail": str(e)},
        )

    try:
        out = device.shell("settings get global adb_enabled").strip()
        if out == "1":
            checks.append(
                {
                    "name": "adb_enabled",
                    "status": "warn",
                    "detail": "settings.global.adb_enabled=1 -- detectable but unavoidable",
                }
            )
        else:
            checks.append({"name": "adb_enabled", "status": "pass"})
    except Exception as e:  # noqa: BLE001
        checks.append({"name": "adb_enabled", "status": "warn", "detail": str(e)})

    return checks
