"""Douyin app plugin (抖音). Selectors per research/ui-trees/douyin/00-selectors.md."""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import Any

from mobilecli.envelope import EmError, ErrorCode
from mobilecli.plugin import App, ExecContext

PACKAGE = "com.ss.android.ugc.aweme"

app = App(
    name="douyin",
    package=PACKAGE,
    daily_caps={
        "comment": 100,
        "follow": 100,
        "dm": 100,
        "like": 200,
    },
    extra_lint_patterns=[],
)


# ----- launch ------------------------------------------------------------------


@app.verb("launch")
def launch(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Launch Douyin and return the resulting foreground package + activity."""
    ctx.app.launch()
    time.sleep(3)
    return {"foreground": ctx.app.foreground(), "package": PACKAGE}


# ----- search ------------------------------------------------------------------


def _search_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--keyword", required=True)
    p.add_argument("--limit", type=int, default=10)


@app.verb("search", add_args=_search_args)
def search(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Search videos. Returns a result list; does NOT tap any result."""
    ctx.app.ensure_foreground()
    time.sleep(1.5)

    # 1. Tap search icon (content-desc="搜索")
    xml = Path(ctx.ui.dump()["path"]).read_text()
    node = ctx.ui.find_by_content_desc(xml, "搜索")
    if node is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "search icon not on home screen",
            hint="run `mobilecli dump` to inspect; UI may have changed",
        )
    ctx.input.tap_node(node)
    time.sleep(2)

    # 2. Tap input box, type keyword
    xml = Path(ctx.ui.dump()["path"]).read_text()
    inp = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/et_search_kw")
    if inp is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "search input not found")
    ctx.input.tap_node(inp)
    time.sleep(0.8)
    ctx.input.type_text(args.keyword)
    time.sleep(1.2)
    ctx.input.keyevent(66)  # KEYCODE_ENTER
    time.sleep(3)

    # 3. Parse result cards (resource-id q21)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    cards = ctx.ui.find_all_by_resource_id(xml, "com.ss.android.ugc.aweme:id/q21")
    results = []
    for i, c in enumerate(cards[: args.limit], 1):
        results.append(
            {
                "index": i,
                "cx": c["cx"],
                "cy": c["cy"],
                "bounds": c["bounds"],
            }
        )
    return {"keyword": args.keyword, "results": results}


# ----- open --------------------------------------------------------------------


def _open_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rank", type=int, required=True)


@app.verb("open", add_args=_open_args)
def open_result(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Tap the Nth search result card from the current results screen."""
    xml = Path(ctx.ui.dump()["path"]).read_text()
    cards = ctx.ui.find_all_by_resource_id(xml, "com.ss.android.ugc.aweme:id/q21")
    if args.rank < 1 or args.rank > len(cards):
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            f"rank {args.rank} out of range (have {len(cards)} cards)",
            hint="run `mobilecli douyin search` first",
        )
    ctx.input.tap_node(cards[args.rank - 1])
    time.sleep(3)

    # Switch to single-column for stable comment access
    xml = Path(ctx.ui.dump()["path"]).read_text()
    toggle = ctx.ui.find_by_content_desc(xml, "单双列切换图标")
    if toggle is not None:
        ctx.input.tap_node(toggle)
        time.sleep(2)
    return {"rank": args.rank, "foreground": ctx.app.foreground()}


# ----- detail ------------------------------------------------------------------

_COUNT_RE = re.compile(r"(\d+(?:\.\d+)?[万亿]?)")


def _parse_count(s: str) -> str:
    m = _COUNT_RE.search(s or "")
    return m.group(1) if m else ""


@app.verb("detail")
def detail(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Read like / comment / share / collect counts from the current video detail."""
    xml = Path(ctx.ui.dump()["path"]).read_text()
    like = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/gl1")
    comment = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/eql")
    share = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/zk8")
    collect = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/d_7")
    return {
        "likes": _parse_count(like["content_desc"]) if like else "",
        "comments": _parse_count(comment["content_desc"]) if comment else "",
        "shares": _parse_count(share["content_desc"]) if share else "",
        "collects": _parse_count(collect["content_desc"]) if collect else "",
    }


# ----- back --------------------------------------------------------------------


@app.verb("back")
def back(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Press the system back button (recovery primitive used between iterations)."""
    ctx.input.keyevent("back")
    time.sleep(0.6)
    return {"foreground": ctx.app.foreground()}


# ----- comment -----------------------------------------------------------------


def _comment_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--text", required=True)


@app.verb("comment", add_args=_comment_args, requires_commit_flag=True)
def comment(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Comment on the current video detail.

    Default = dry-run (open compose, type text, locate send button, cancel).
    With --commit (and EM_ALLOW_COMMIT=1 gated by cli), actually press send.
    """
    ctx.linter.check_or_raise(args.text)
    ctx.governor.check_or_raise("comment")

    xml = Path(ctx.ui.dump()["path"]).read_text()
    inp = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/eoy")
    if inp is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "comment input not visible",
            hint="open a video detail first via `douyin open --rank N`",
        )
    ctx.input.tap_node(inp)
    time.sleep(1.5)
    ctx.input.type_text(args.text)
    time.sleep(1.5)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    send_btn = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/es1")
    if send_btn is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "send button did not appear",
            hint="text may not have been entered; check IME with `doctor`",
        )

    if not getattr(args, "commit", False):
        ctx.input.keyevent("back")
        return {
            "dry_run": True,
            "committed": False,
            "text": args.text,
            "send_button_cx": send_btn["cx"],
            "send_button_cy": send_btn["cy"],
        }

    ctx.input.tap_node(send_btn)
    time.sleep(4)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    verified = args.text in xml
    ctx.governor.record("comment")
    return {
        "dry_run": False,
        "committed": True,
        "verified_visible": verified,
        "text": args.text,
    }
