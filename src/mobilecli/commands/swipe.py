"""`mobilecli swipe X1 Y1 X2 Y2 [--duration N]` command."""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.adb.device import Device
from mobilecli.core import input as core_input
from mobilecli.envelope import envelope


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("swipe", help="Swipe gesture")
    p.add_argument("x1", type=int)
    p.add_argument("y1", type=int)
    p.add_argument("x2", type=int)
    p.add_argument("y2", type=int)
    p.add_argument("--duration", type=int, default=300, help="ms (default 300)")


@envelope(command="swipe")
def _run(
    *,
    device: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration: int,
    raw: bool,
) -> dict[str, Any]:
    dev = Device.from_serial(device or None)
    if raw:
        return core_input.swipe_raw(dev, x1, y1, x2, y2, duration)
    return core_input.swipe_humanized(dev, (x1, y1), (x2, y2))


def run(args: argparse.Namespace) -> str:
    return _run(
        device=args.serial or "",
        x1=args.x1,
        y1=args.y1,
        x2=args.x2,
        y2=args.y2,
        duration=args.duration,
        raw=args.raw,
    )
