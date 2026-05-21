"""`mobilecli foreground`."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import app as core_app
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    subparsers.add_parser("foreground", help="Current foreground package + activity")


@envelope(command="foreground")
def _run(*, device: str) -> dict[str, Any]:
    dev = Device.from_serial(device or None)
    return core_app.foreground(dev)


def run(args: argparse.Namespace) -> str:
    return _run(device=args.serial or "")
