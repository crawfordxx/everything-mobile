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
    dev = Device.from_serial(device or None)
    return core_app.launch(dev, package)


def run(args: argparse.Namespace) -> str:
    return _run(device=args.serial or "", package=args.package)
