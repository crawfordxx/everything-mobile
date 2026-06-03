"""IME (input method) helpers -- ADBKeyboard installation + activation."""

from __future__ import annotations

import shlex
import time
from collections.abc import Callable

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


def clear_and_input(device: Device, keyword: str, focus: Callable[[], None]) -> None:
    """稳妥地把搜索词打进输入框:切到 ADBKeyboard → 聚焦输入框(focus 回调)→ 清空
    旧内容 → 输入关键词 → 还原原输入法。`focus` 在切到 ADBKeyboard 之后调用,确保输入
    框拿到 ADBKeyboard 的输入连接。

    解决两类老问题:
    1. ascii 关键词此前走 `input text` 且不清空,会拼在残留词后面 —— 搜「AI」却命中上
       一次的「护肤」。
    2. 中文关键词若没切 ADBKeyboard 根本打不进去。
    ADBKeyboard 的 ADB_CLEAR_TEXT / ADB_INPUT_TEXT 广播对中英文都生效,统一走它最稳。
    调用方在本函数返回后再提交(回车 / 点「搜索」按钮)。
    """
    prev = current_ime(device)
    set_adbkeyboard(device)
    time.sleep(0.6)
    try:
        focus()
        time.sleep(0.8)
        device.shell("am broadcast -a ADB_CLEAR_TEXT")
        time.sleep(0.3)
        device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(keyword)}")
        time.sleep(1.0)
    finally:
        restore_ime(device, prev)
