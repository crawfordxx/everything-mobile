"""`mobilecli screenshot` command."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import screenshot
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("screenshot", help="Capture screen to PNG")
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output path (default /tmp/em-screen-*.png)",
    )


@envelope(command="screenshot")
def _run(*, device: str, output: str | None) -> dict[str, Any]:
    dev = Device.from_serial(device or None)
    return screenshot.capture(dev, output)


def run(args: argparse.Namespace) -> str:
    return _run(device=args.serial or "", output=args.output)
