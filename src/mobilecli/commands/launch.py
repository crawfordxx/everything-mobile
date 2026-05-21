"""`mobilecli launch <package>`."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import app as core_app
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("launch", help="Launch an app by package name")
    p.add_argument("package")


@envelope(command="launch")
def _run(*, device: str, package: str) -> dict[str, Any]:
    dev = Device(serial=device)
    return core_app.launch(dev, package)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial, package=args.package)
