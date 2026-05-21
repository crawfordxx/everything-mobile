"""`mobilecli devices` -- list connected devices."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    subparsers.add_parser("devices", help="List connected devices")


@envelope(command="devices")
def _run(device: str = "") -> dict[str, Any]:
    devs = Device.list_attached()
    return {"devices": devs}


def run(args: argparse.Namespace) -> str:
    return _run(device="")
