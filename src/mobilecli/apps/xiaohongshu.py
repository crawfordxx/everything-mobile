"""Xiaohongshu app plugin (小红书).

Selectors per research/ui-trees/xiaohongshu/00-selectors.md.

NOTE: v1 comment verb is DRY-RUN ONLY. Spec §6 lock: 个人号 not allowed to
post via this library in v1. The verb writes into the compose box and locates
the send button, then presses back. There is no --commit flag.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import Any

from mobilecli.envelope import EmError, ErrorCode
from mobilecli.plugin import App, ExecContext

PACKAGE = "com.xingin.xhs"

app = App(
    name="xiaohongshu",
    package=PACKAGE,
    daily_caps={
        "comment": 20,
        "dm": 30,
        "follow": 30,
        "like": 100,
    },
    extra_lint_patterns=[],
)


# Home-state oracle (UI-tree research: home is IndexActivityV2).
_HOME_ACTIVITY_SUFFIX = ".IndexActivityV2"


def _on_home(ctx: ExecContext) -> bool:
    activity = str(ctx.app.foreground().get("activity", ""))
    return activity.endswith(_HOME_ACTIVITY_SUFFIX)


def _ensure_home(ctx: ExecContext, max_back: int = 5) -> dict[str, Any]:
    """Force Xiaohongshu to home (IndexActivityV2).

    Escalating strategy: foreground → back-N → force-stop + relaunch. Also
    recovers from the first-launch login wall.
    """
    ctx.app.ensure_foreground()
    time.sleep(0.5)
    fg = ctx.app.foreground()
    if "DeviceOfflineRemindActivity" in fg.get("activity", ""):
        ctx.input.keyevent("back")
        time.sleep(1)
        ctx.app.launch()
        time.sleep(3)
    for _ in range(max_back):
        if _on_home(ctx):
            return ctx.app.foreground()
        ctx.input.keyevent("back")
        time.sleep(0.8)
    if not _on_home(ctx):
        ctx.app.force_stop()
        time.sleep(0.8)
        ctx.app.launch()
        time.sleep(3.5)
    return ctx.app.foreground()


# ----- launch ------------------------------------------------------------------


@app.verb("launch")
def launch(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Launch Xiaohongshu and force-navigate to the home feed.

    Recovers from the first-launch login wall if encountered.
    """
    fg = _ensure_home(ctx)
    return {"foreground": fg, "package": PACKAGE, "on_home": _on_home(ctx)}


# ----- search ------------------------------------------------------------------


def _search_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--keyword", required=True)
    p.add_argument("--limit", type=int, default=10)


@app.verb("search", add_args=_search_args)
def search(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Search notes. Returns a result list; does NOT tap any result.

    Forces the app to its home feed first, regardless of where it was left.
    """
    _ensure_home(ctx)
    time.sleep(1.0)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    search_node = ctx.ui.find_by_resource_id(
        xml,
        "com.xingin.xhs:id/mSearchToolBarSearchBtn",
    )
    if search_node is None:
        search_node = ctx.ui.find_by_content_desc(xml, "搜索")
    if search_node is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "XHS search affordance not found")
    ctx.input.tap_node(search_node)
    time.sleep(2)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    inp = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/mSearchToolBarEt")
    if inp is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "XHS search input not found")
    ctx.input.tap_node(inp)
    time.sleep(0.8)
    ctx.input.type_text(args.keyword)
    time.sleep(1.2)
    ctx.input.keyevent(66)
    time.sleep(3)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    cards = ctx.ui.find_all_by_resource_id(xml, "com.xingin.xhs:id/searchNoteCard")
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
    """Tap the Nth search result note from the current results screen."""
    xml = Path(ctx.ui.dump()["path"]).read_text()
    cards = ctx.ui.find_all_by_resource_id(xml, "com.xingin.xhs:id/searchNoteCard")
    if args.rank < 1 or args.rank > len(cards):
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            f"rank {args.rank} out of range (have {len(cards)})",
        )
    ctx.input.tap_node(cards[args.rank - 1])
    time.sleep(3)
    return {"rank": args.rank, "foreground": ctx.app.foreground()}


# ----- detail ------------------------------------------------------------------

_COUNT_RE = re.compile(r"(\d+)")


def _count(node: dict[str, Any] | None) -> str:
    if not node:
        return ""
    m = _COUNT_RE.search(node.get("content_desc", "") + " " + node.get("text", ""))
    return m.group(1) if m else ""


@app.verb("detail")
def detail(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Read like / comment / collect counts from the current note detail."""
    xml = Path(ctx.ui.dump()["path"]).read_text()
    like = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/noteLikeLayout")
    comment = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/noteCommentLayout")
    collect = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/noteCollectLayout")
    return {
        "likes": _count(like),
        "comments": _count(comment),
        "collects": _count(collect),
    }


# ----- back --------------------------------------------------------------------


@app.verb("back")
def back(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Press the system back button (recovery primitive used between iterations)."""
    ctx.input.keyevent("back")
    time.sleep(0.6)
    return {"foreground": ctx.app.foreground()}


# ----- comment (DRY-RUN ONLY) --------------------------------------------------


def _comment_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--text", required=True)


@app.verb("comment", add_args=_comment_args)  # NO requires_commit_flag — v1 never sends
def comment(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """DRY-RUN ONLY in v1: open compose, type text, locate send button, then back.

    The send button is never tapped. Per spec §6 lock: XHS account is personal,
    not authorized to actually post via this library.
    """
    ctx.linter.check_or_raise(args.text)
    ctx.governor.check_or_raise("comment")

    xml = Path(ctx.ui.dump()["path"]).read_text()
    compose = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/mContentET")
    if compose is None:
        # Try opening compose via the bottom comment CTA
        cta = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/noteCommentLayout")
        if cta is not None:
            ctx.input.tap_node(cta)
            time.sleep(1.5)
            xml = Path(ctx.ui.dump()["path"]).read_text()
            compose = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/mContentET")
    if compose is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "XHS comment compose not visible",
            hint="open a note detail first via `xiaohongshu open --rank N`",
        )

    ctx.input.tap_node(compose)
    time.sleep(1)
    ctx.input.type_text(args.text)
    time.sleep(1.5)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    send_btn = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/commentFuncBtnSend")

    # CRITICAL: never tap. Back out to keep account state clean.
    ctx.input.keyevent("back")
    return {
        "dry_run": True,
        "text": args.text,
        "send_button_cx": send_btn["cx"] if send_btn else None,
        "send_button_cy": send_btn["cy"] if send_btn else None,
        "note": "v1 is dry-run only; send button was never tapped",
    }
