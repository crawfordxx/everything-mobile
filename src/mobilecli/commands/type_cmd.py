"""`mobilecli type "..."` command."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import input as core_input
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("type", help="Type text")
    p.add_argument("text", help="Text to type (ASCII or Chinese)")


@envelope(command="type")
def _run(*, device: str, text: str) -> dict[str, Any]:
    dev = Device(serial=device)
    return core_input.type_text_raw(dev, text)


def run(args: argparse.Namespace) -> str:
    dev = Device.from_serial(args.serial)
    return _run(device=dev.serial, text=args.text)
