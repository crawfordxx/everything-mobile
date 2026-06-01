"""Douyin app plugin (抖音). Selectors per research/ui-trees/douyin/00-selectors.md."""

from __future__ import annotations

import argparse
import re
import shlex
import time
from pathlib import Path
from typing import Any

from mobilecli.apps._comments import CommentRow, select_comment
from mobilecli.core import ime as _ime
from mobilecli.core.ui import (
    find_all_by_resource_id,
    find_by_content_desc,
    find_by_content_desc_contains,
    find_by_resource_id,
    find_first_by_class,
)
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


# Home-state oracle (UI-tree research: home feed lives on SplashActivity).
_HOME_ACTIVITY_SUFFIX = ".SplashActivity"


def _on_home(ctx: ExecContext) -> bool:
    activity = str(ctx.app.foreground().get("activity", ""))
    return activity.endswith(_HOME_ACTIVITY_SUFFIX)


def _ensure_home(ctx: ExecContext, max_back: int = 5) -> dict[str, Any]:
    """Force Douyin to its home feed.

    Strategy in escalating strength:
    1. Ensure foreground (monkey-launch if not).
    2. Press back up to max_back times — usually unwinds detail / search stacks.
    3. If still not on SplashActivity: `am force-stop` to kill the task entirely,
       then re-launch. This recovers from stale tasks where monkey-launch
       just brings the previous DetailActivity back to top.
    """
    ctx.app.ensure_foreground()
    time.sleep(0.5)
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


_DY_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([万亿]?)")


def _to_int(s: str) -> int:
    """'3046'->3046; '1.2万'->12000; '抖音号' 等非数字 -> 0。"""
    m = _DY_NUM_RE.search(s or "")
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "万":
        val *= 10_000
    elif unit == "亿":
        val *= 100_000_000
    return int(val)


def _parse_douyin_profile(xml: str) -> dict[str, Any]:
    """Parse Douyin 我 tab. logged_in oracle = 用户头像 / 昵称 present."""
    PFX = "com.ss.android.ugc.aweme:id/"
    avatar = find_by_content_desc(xml, "用户头像")
    nick = find_by_resource_id(xml, PFX + "tdp")
    if avatar is None and nick is None:
        return {"logged_in": False}

    did = find_by_resource_id(xml, PFX + "5no")
    likes = find_by_resource_id(xml, PFX + "5yp")
    following = find_by_resource_id(xml, PFX + "5yw")
    fans = find_by_resource_id(xml, PFX + "5yi")

    def _txt(node: dict[str, Any] | None) -> str:
        return (node.get("text") or "").strip() if node else ""

    did_txt = _txt(did).replace("抖音号：", "").replace("抖音号:", "").strip()
    return {
        "logged_in": True,
        "nickname": _txt(nick),
        "douyin_id": did_txt,
        "following_count": _to_int(_txt(following)),
        "fans_count": _to_int(_txt(fans)),
        "likes_count": _to_int(_txt(likes)),
        "avatar_bounds": tuple(avatar["bounds"]) if avatar else None,
    }


# ----- launch ------------------------------------------------------------------


@app.verb("launch")
def launch(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Launch Douyin and force-navigate to the home feed."""
    fg = _ensure_home(ctx)
    return {"foreground": fg, "package": PACKAGE, "on_home": _on_home(ctx)}


# ----- search ------------------------------------------------------------------


def _search_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--keyword", required=True)
    p.add_argument("--limit", type=int, default=10)


@app.verb("search", add_args=_search_args)
def search(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Search videos. Returns a result list; does NOT tap any result.

    Forces the app to its home feed first, regardless of where it was left.
    """
    _ensure_home(ctx)
    time.sleep(1.0)

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
    ctx.input.idle_browse()
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
    ctx.input.reading_pause()
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


# ----- like ---------------------------------------------------------------------


@app.verb("like", requires_commit_flag=True)
def like(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Like the current video detail.

    Default = dry-run (locate like button, return coords).
    With --commit (and EM_ALLOW_COMMIT=1 gated by cli), actually tap.
    """
    ctx.governor.check_or_raise("like")

    # Locate by content-desc ("未点赞，喜欢N，按钮") so it works on both video
    # detail (gl1) and photo-flow (qjl) layouts.
    xml = Path(ctx.ui.dump()["path"]).read_text()
    like_btn = find_by_content_desc_contains(xml, "喜欢", "按钮")
    if like_btn is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "Douyin like button not visible",
            hint="open a video / photo detail first via `douyin open --rank N`",
        )

    before_liked = "已点赞" in like_btn.get("content_desc", "")

    if not getattr(args, "commit", False):
        return {
            "dry_run": True,
            "committed": False,
            "already_liked": before_liked,
            "like_button_cx": like_btn["cx"],
            "like_button_cy": like_btn["cy"],
        }

    ctx.input.tap_node(like_btn)
    time.sleep(1.5)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    after = find_by_content_desc_contains(xml, "喜欢", "按钮")
    after_liked = "已点赞" in (after.get("content_desc", "") if after else "")
    ctx.governor.record("like")
    return {
        "dry_run": False,
        "committed": True,
        "already_liked_before": before_liked,
        "already_liked_after": after_liked,
        "verified_changed": before_liked != after_liked,
    }


# ----- comments (shared parse for reply) ----------------------------------------

_FCO_ID = "com.ss.android.ugc.aweme:id/fco"
_XDH_ID = "com.ss.android.ugc.aweme:id/xdh"


def _bounds_contains(outer: list[int] | None, cx: int, cy: int) -> bool:
    if not outer:
        return False
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def _parse_comment_rows(xml: str) -> list[CommentRow]:
    """Parse top-level comment rows from the comments overlay.

    Each top-level comment is an `fco` FrameLayout whose content-desc is the
    whole comment string; its 回复 button is an `xdh` inside it. Anchor on xdh
    (guarantees a tappable target) and pair to the enclosing fco for text.
    Partially-scrolled last rows have an fco but no xdh -> naturally dropped.
    """
    fcos = find_all_by_resource_id(xml, _FCO_ID)
    xdhs = find_all_by_resource_id(xml, _XDH_ID)
    rows: list[CommentRow] = []
    for xdh in xdhs:
        container = next(
            (f for f in fcos if _bounds_contains(f["bounds"], xdh["cx"], xdh["cy"])),
            None,
        )
        text = container["content_desc"] if container else ""
        rows.append(CommentRow(index=len(rows) + 1, text=text, reply_node=xdh))
    return rows


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


# ----- reply (二级追评) ---------------------------------------------------------


def _reply_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rank", type=int, help="reply to the Nth visible comment")
    p.add_argument("--match", help="reply to first visible comment containing this text")
    p.add_argument("--text", required=True)


@app.verb("reply", add_args=_reply_args, requires_commit_flag=True)
def reply(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Reply to a comment on the current video (creates a 2nd-level reply).

    Select target by --rank N or --match "kw" (exactly one). Default = dry-run
    (locate target + send button, cancel). --commit actually sends.
    """
    ctx.linter.check_or_raise(args.text)
    ctx.governor.check_or_raise("comment")

    # Ensure the comments overlay is open (parse; if empty, tap comment icon).
    xml = Path(ctx.ui.dump()["path"]).read_text()
    rows = _parse_comment_rows(xml)
    if not rows:
        cmt = find_by_content_desc_contains(xml, "评论", "按钮")
        if cmt is None:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "comment entry not visible",
                hint="open a video / photo detail first via `douyin open --rank N`",
            )
        ctx.input.tap_node(cmt)
        time.sleep(2)
        xml = Path(ctx.ui.dump()["path"]).read_text()
        rows = _parse_comment_rows(xml)

    target = select_comment(rows, rank=args.rank, match=args.match)

    # CJK: pre-swap ADBKeyboard BEFORE opening compose; an IME switch while the
    # compose is open dismisses it (same quirk handled in xiaohongshu.comment).
    needs_cjk = not args.text.isascii()
    prev_ime = _ime.current_ime(ctx.device) if needs_cjk else None
    if needs_cjk:
        _ime.set_adbkeyboard(ctx.device)
        time.sleep(0.6)

    try:
        # Tap the row's 回复 button -> opens compose targeted at that comment.
        ctx.input.tap_node(target.reply_node)
        time.sleep(1.5)

        xml = Path(ctx.ui.dump()["path"]).read_text()
        inp = ctx.ui.find_by_resource_id(
            xml, "com.ss.android.ugc.aweme:id/eoy"
        ) or find_first_by_class(xml, "EditText")
        if inp is None:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "reply input not visible",
                hint="tapping 回复 did not open the compose box",
            )
        ctx.input.tap_node(inp)
        time.sleep(1.0)
        if needs_cjk:
            ctx.device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(args.text)}")
        else:
            ctx.input.type_text(args.text)
        time.sleep(1.5)

        xml = Path(ctx.ui.dump()["path"]).read_text()
        send_btn = ctx.ui.find_by_text(xml, "发送")  # robust across es1/es7/photo layouts
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
                "target_index": target.index,
                "target_text": target.text,
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
            "target_index": target.index,
            "text": args.text,
        }
    finally:
        if needs_cjk and prev_ime:
            _ime.restore_ime(ctx.device, prev_ime)


# ----- profile -----------------------------------------------------------------


_ME_TAB_XY = (972, 2282)  # 抖音底部导航 "我" (id/0r4)


def _profile_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--avatar-out", default=None, help="头像 PNG 落盘路径")


@app.verb("profile", add_args=_profile_args)
def profile(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """读取抖音登录态;已登录则返回头像(裁剪PNG)/昵称/抖音号/关注·粉丝·获赞数。"""
    _ensure_home(ctx)
    ctx.input.tap_xy(*_ME_TAB_XY)
    time.sleep(2.5)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    info = _parse_douyin_profile(xml)
    if not info.get("logged_in"):
        return {"logged_in": False}
    bounds = info.pop("avatar_bounds", None)
    if bounds is not None:
        info["avatar"] = ctx.ui.screenshot_region(bounds, args.avatar_out)["path"]
    else:
        info["avatar"] = None
    return info
