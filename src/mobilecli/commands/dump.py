"""`mobilecli dump` command."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import ui
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("dump", help="uiautomator dump -> XML path")
    p.add_argument("-o", "--output", default=None)


@envelope(command="dump")
def _run(*, device: str, output: str | None) -> dict[str, Any]:
    dev = Device.from_serial(device or None)
    return ui.dump(dev, output)


def run(args: argparse.Namespace) -> str:
    return _run(device=args.serial or "", output=args.output)
