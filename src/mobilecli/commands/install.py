"""`mobilecli install <apk_path>`."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import app as core_app
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("install", help="adb install -r")
    p.add_argument("apk")


@envelope(command="install")
def _run(*, device: str, apk: str) -> dict[str, Any]:
    dev = Device(serial=device)
    return core_app.install(dev, apk)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial, apk=args.apk)
