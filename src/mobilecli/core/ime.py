"""IME (input method) helpers -- ADBKeyboard installation + activation."""

from __future__ import annotations

from mobilecli.adb.device import Device
from mobilecli.envelope import EmError, ErrorCode

ADBKEYBOARD_ID = "com.android.adbkeyboard/.AdbIME"


def list_imes(device: Device) -> list[str]:
    out = device.shell("ime list -s")
    return [line.strip() for line in out.splitlines() if line.strip()]


def current_ime(device: Device) -> str:
    return device.shell("settings get secure default_input_method").strip()


def set_adbkeyboard(device: Device) -> None:
    if ADBKEYBOARD_ID not in list_imes(device):
        raise EmError(
            ErrorCode.IME_NOT_SET,
            "ADBKeyboard not installed on device",
            hint="install from https://github.com/senzhk/ADBKeyBoard",
        )
    device.shell(f"ime set {ADBKEYBOARD_ID}")


def restore_ime(device: Device, previous: str) -> None:
    if previous and previous != ADBKEYBOARD_ID:
        device.shell(f"ime set {previous}")
