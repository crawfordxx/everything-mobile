"""`mobilecli tap X Y` command."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import input as core_input
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("tap", help="Tap at absolute coords")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)


@envelope(command="tap")
def _run(*, device: str, x: int, y: int) -> dict[str, Any]:
    dev = Device.from_serial(device or None)
    return core_input.tap_raw(dev, x, y)


def run(args: argparse.Namespace) -> str:
    return _run(device=args.serial or "", x=args.x, y=args.y)
