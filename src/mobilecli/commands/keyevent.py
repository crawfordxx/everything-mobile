"""`mobilecli keyevent {back|home|enter|recent|menu|...}` command."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import input as core_input
from mobilecli.envelope import envelope

KEY_ALIASES: dict[str, int] = {
    "back": 4,
    "home": 3,
    "enter": 66,
    "recent": 187,
    "menu": 82,
    "power": 26,
    "volume_up": 24,
    "volume_down": 25,
    "dpad_up": 19,
    "dpad_down": 20,
    "dpad_left": 21,
    "dpad_right": 22,
    "tab": 61,
    "del": 67,
    "space": 62,
}


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("keyevent", help="Send a keyevent")
    p.add_argument(
        "key",
        help="Alias (back/home/enter/recent/menu/...) or numeric KEYCODE",
    )


@envelope(command="keyevent")
def _run(*, device: str, key: str) -> dict[str, Any]:
    dev = Device(serial=device)
    code: int | str = KEY_ALIASES.get(key.lower(), key)
    return core_input.keyevent_raw(dev, code)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial, key=args.key)
