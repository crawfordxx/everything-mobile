"""Shared feed-swipe verb logic for douyin / kuaishou.

短视频 feed 都靠上下滑切换内容;几何/人性化细节在 InputModule.swipe_feed,
这里只做参数面 + 次数循环,供各 app 注册 `swipe` verb 复用。
"""

from __future__ import annotations

import argparse
from typing import Any

from mobilecli.envelope import EmError, ErrorCode
from mobilecli.plugin.ctx import ExecContext

_MAX_TIMES = 20


def swipe_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--direction", choices=("up", "down"), default="up", help="up=看下一条(默认)")
    p.add_argument("--times", type=int, default=1, help=f"连滑次数(1~{_MAX_TIMES})")


def run_swipe(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """连滑 N 次;每次之间由 InputModule 的 pace 提供人为停顿。"""
    if args.times < 1 or args.times > _MAX_TIMES:
        raise EmError(
            ErrorCode.INVALID_ARG,
            f"--times {args.times} out of range",
            hint=f"1~{_MAX_TIMES};更长的刷流请分多次调用",
        )
    moves = [ctx.input.swipe_feed(args.direction) for _ in range(args.times)]
    return {
        "direction": args.direction,
        "times": args.times,
        "moves": moves,
        "foreground": ctx.app.foreground(),
    }
