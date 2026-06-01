"""Kuaishou app plugin (快手). Selectors per research/ui-trees/kuaishou/00-selectors.md.

Notes specific to Kuaishou:
- The video detail (`PhotoDetailActivity`) never reaches uiautomator "idle" while
  the feed/video animates, so `uiautomator dump` fails ("could not get idle
  state"). Disabling the three global animation scales makes dumps succeed.
  `_disable_animations` is called by launch and every dump-dependent verb.
- Launch lands on the last-viewed tab + interstitial popups (勋章 / 推送通知);
  `_dismiss_popups` taps 忽略 to clear them, then we switch to the 首页 feed.
- Comment overlay rows are clean: each `comment_frame` ∋ `comment` (text) +
  `comment_reply` (回复). reply compose = `editor` + `finish_button` (发送).
"""

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
    find_by_resource_id,
    find_first_by_class,
)
from mobilecli.envelope import EmError, ErrorCode
from mobilecli.plugin import App, ExecContext

PACKAGE = "com.smile.gifmaker"

app = App(
    name="kuaishou",
    package=PACKAGE,
    daily_caps={
        "comment": 100,
        "follow": 100,
        "dm": 100,
        "like": 200,
    },
    extra_lint_patterns=[],
)

_HOME_ACTIVITY_SUFFIX = ".HomeActivity"
_SEARCH_BTN = "com.smile.gifmaker:id/search_btn"
_EDITOR = "com.smile.gifmaker:id/editor"
_PLAY_CONTAINER = "com.smile.gifmaker:id/play_view_container"
_LIKE_BTN = "com.smile.gifmaker:id/like_button"
_COMMENT_BTN = "com.smile.gifmaker:id/comment_button"
_FINISH_BTN = "com.smile.gifmaker:id/finish_button"
_COMMENT_FRAME = "com.smile.gifmaker:id/comment_frame"
_COMMENT_TEXT = "com.smile.gifmaker:id/comment"
# NOTE: the 回复 button lives under a different package prefix than the row.
_COMMENT_REPLY = "com.smile.gifmaker.comment_detail:id/comment_reply"

_COUNT_RE = re.compile(r"(\d+(?:\.\d+)?[万亿]?)")


def _digits(node: dict[str, Any] | None) -> str:
    if not node:
        return ""
    m = _COUNT_RE.search(node.get("content_desc", "") + " " + node.get("text", ""))
    return m.group(1) if m else ""


def _center_in(outer: list[int] | None, inner: list[int] | None) -> bool:
    if not outer or not inner:
        return False
    icx = (inner[0] + inner[2]) // 2
    icy = (inner[1] + inner[3]) // 2
    return outer[0] <= icx <= outer[2] and outer[1] <= icy <= outer[3]


def _disable_animations(ctx: ExecContext) -> None:
    """Zero the global animation scales so uiautomator dump can reach idle.

    Required for Kuaishou's autoplaying detail / overlay screens. Persists on
    the device (benign for an automation device)."""
    for key in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
        try:
            ctx.device.shell(f"settings put global {key} 0")
        except EmError:
            pass


def _dismiss_popups(ctx: ExecContext, max_rounds: int = 3) -> None:
    """Tap 忽略 to clear interstitial popups (勋章 / 推送通知 / etc)."""
    for _ in range(max_rounds):
        try:
            xml = Path(ctx.ui.dump()["path"]).read_text()
        except EmError:
            return
        btn = ctx.ui.find_by_text(xml, "忽略")
        if btn is None:
            return
        ctx.input.tap_node(btn)
        time.sleep(1.0)


def _on_home(ctx: ExecContext) -> bool:
    return str(ctx.app.foreground().get("activity", "")).endswith(_HOME_ACTIVITY_SUFFIX)


def _ensure_home(ctx: ExecContext) -> dict[str, Any]:
    """Force Kuaishou to the 首页 feed (where the 查找 search entry lives)."""
    ctx.app.ensure_foreground()
    time.sleep(0.5)
    _disable_animations(ctx)
    _dismiss_popups(ctx)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    home_tab = ctx.ui.find_by_content_desc(xml, "首页")
    if home_tab is not None:
        ctx.input.tap_node(home_tab)
        time.sleep(1.5)
    return ctx.app.foreground()


_KS_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([万亿]?)")


def _to_int(s: str) -> int:
    """'15'->15; content-desc '粉丝数，1个'->1; '1.2万'->12000。"""
    m = _KS_NUM_RE.search(s or "")
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "万":
        val *= 10_000
    elif unit == "亿":
        val *= 100_000_000
    return int(val)


def _parse_kuaishou_profile(xml: str) -> dict[str, Any]:
    """Parse Kuaishou 我 tab. logged_in oracle = 昵称/快手号 present.
    粉丝/关注/获赞 counts live in the *_layout node's content-desc."""
    PFX = "com.smile.gifmaker:id/"
    nick = find_by_resource_id(xml, PFX + "user_name_tv")
    kwai = find_by_resource_id(xml, PFX + "profile_user_kwai_id")
    if nick is None and kwai is None:
        return {"logged_in": False}

    follower = find_by_resource_id(xml, PFX + "follower_layout")
    following = find_by_resource_id(xml, PFX + "following_layout")
    like = find_by_resource_id(xml, PFX + "like_layout")
    bio = find_by_resource_id(xml, PFX + "user_text")
    avatar = find_by_resource_id(xml, PFX + "avatar")

    def _txt(node: dict[str, Any] | None) -> str:
        return (node.get("text") or "").strip() if node else ""

    def _desc(node: dict[str, Any] | None) -> str:
        return (node.get("content_desc") or "") if node else ""

    kwai_txt = _txt(kwai).replace("快手号：", "").replace("快手号:", "").strip()
    return {
        "logged_in": True,
        "nickname": _txt(nick),
        "kwai_id": kwai_txt,
        "following_count": _to_int(_desc(following)),
        "fans_count": _to_int(_desc(follower)),
        "likes_count": _to_int(_desc(like)),
        "bio": _txt(bio),
        "avatar_bounds": tuple(avatar["bounds"]) if avatar else None,
    }


# ----- launch ------------------------------------------------------------------


@app.verb("launch")
def launch(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Launch Kuaishou, disable animation scales, clear popups, go to 首页 feed."""
    fg = _ensure_home(ctx)
    return {"foreground": fg, "package": PACKAGE, "on_home": _on_home(ctx)}


# ----- search ------------------------------------------------------------------


def _search_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--keyword", required=True)
    p.add_argument("--limit", type=int, default=10)


@app.verb("search", add_args=_search_args)
def search(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Search videos. Returns a result list; does NOT tap any result."""
    _ensure_home(ctx)
    time.sleep(0.8)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    sb = ctx.ui.find_by_resource_id(xml, _SEARCH_BTN) or ctx.ui.find_by_content_desc(xml, "查找")
    if sb is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "kuaishou search entry (查找) not found on home feed",
            hint="run `mobilecli dump` to inspect; UI may have changed",
        )
    ctx.input.tap_node(sb)
    time.sleep(2)
    _dismiss_popups(ctx)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    inp = ctx.ui.find_by_resource_id(xml, _EDITOR)
    if inp is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "kuaishou search input not found")

    needs_cjk = not args.keyword.isascii()
    prev_ime = _ime.current_ime(ctx.device) if needs_cjk else None
    if needs_cjk:
        _ime.set_adbkeyboard(ctx.device)
        time.sleep(0.6)
    try:
        ctx.input.tap_node(inp)
        time.sleep(1.0)
        if needs_cjk:
            ctx.device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(args.keyword)}")
        else:
            ctx.input.type_text(args.keyword)
        time.sleep(1.2)
        xml = Path(ctx.ui.dump()["path"]).read_text()
        submit = ctx.ui.find_by_text(xml, "搜索")
        if submit is not None:
            ctx.input.tap_node(submit)
        else:
            ctx.input.keyevent(66)  # KEYCODE_ENTER
        time.sleep(3)
    finally:
        if needs_cjk and prev_ime:
            _ime.restore_ime(ctx.device, prev_ime)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    cards = [
        c for c in find_all_by_resource_id(xml, _PLAY_CONTAINER)
        if c["bounds"] and (c["bounds"][2] - c["bounds"][0]) > 100  # drop off-screen sliver cards
    ]
    results = [
        {"index": i, "cx": c["cx"], "cy": c["cy"], "bounds": c["bounds"]}
        for i, c in enumerate(cards[: args.limit], 1)
    ]
    return {"keyword": args.keyword, "results": results}


# ----- open --------------------------------------------------------------------


def _open_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rank", type=int, required=True)


@app.verb("open", add_args=_open_args)
def open_result(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Tap the Nth search result card from the current results screen."""
    xml = Path(ctx.ui.dump()["path"]).read_text()
    cards = [
        c for c in find_all_by_resource_id(xml, _PLAY_CONTAINER)
        if c["bounds"] and (c["bounds"][2] - c["bounds"][0]) > 100
    ]
    if args.rank < 1 or args.rank > len(cards):
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            f"rank {args.rank} out of range (have {len(cards)} cards)",
            hint="run `mobilecli kuaishou search` first",
        )
    ctx.input.tap_node(cards[args.rank - 1])
    time.sleep(3)
    _disable_animations(ctx)
    ctx.input.idle_browse()
    return {"rank": args.rank, "foreground": ctx.app.foreground()}


# ----- detail ------------------------------------------------------------------


@app.verb("detail")
def detail(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Read like / comment counts from the current video detail."""
    _disable_animations(ctx)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    ctx.input.reading_pause()
    return {
        "likes": _digits(ctx.ui.find_by_resource_id(xml, _LIKE_BTN)),
        "comments": _digits(ctx.ui.find_by_resource_id(xml, _COMMENT_BTN)),
    }


# ----- back --------------------------------------------------------------------


@app.verb("back")
def back(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Press the system back button (recovery primitive used between iterations)."""
    ctx.input.keyevent("back")
    time.sleep(0.6)
    return {"foreground": ctx.app.foreground()}


# ----- like --------------------------------------------------------------------


@app.verb("like", requires_commit_flag=True)
def like(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Like the current video detail.

    Default = dry-run (locate like button, return coords).
    With --commit (and EM_ALLOW_COMMIT=1 gated by cli), actually tap.
    """
    ctx.governor.check_or_raise("like")
    _disable_animations(ctx)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    like_btn = ctx.ui.find_by_resource_id(xml, _LIKE_BTN)
    if like_btn is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "kuaishou like button not visible",
            hint="open a video detail first via `kuaishou open --rank N`",
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
    after = ctx.ui.find_by_resource_id(xml, _LIKE_BTN)
    after_liked = "已点赞" in (after.get("content_desc", "") if after else "")
    ctx.governor.record("like")
    return {
        "dry_run": False,
        "committed": True,
        "already_liked_before": before_liked,
        "already_liked_after": after_liked,
        "verified_changed": before_liked != after_liked,
    }


# ----- comments (shared parse for comment / reply) ------------------------------


def _parse_comment_rows(xml: str) -> list[CommentRow]:
    """Parse comment rows from the comments overlay.

    Each row = a `comment_frame` container holding a `comment` (text) and a
    `comment_reply` (回复) button. Anchor on the frame; pair the comment +
    reply nodes whose centers fall inside it. Frames without a reply button
    (partially scrolled) are dropped.
    """
    frames = find_all_by_resource_id(xml, _COMMENT_FRAME)
    comments = find_all_by_resource_id(xml, _COMMENT_TEXT)
    replies = find_all_by_resource_id(xml, _COMMENT_REPLY)
    rows: list[CommentRow] = []
    for frame in frames:
        fb = frame["bounds"]
        reply = next((r for r in replies if _center_in(fb, r["bounds"])), None)
        if reply is None:
            continue
        content = next((c for c in comments if _center_in(fb, c["bounds"])), None)
        rows.append(
            CommentRow(
                index=len(rows) + 1,
                text=content["text"] if content else "",
                reply_node=reply,
                content_node=content,
            )
        )
    return rows


def _open_comments(ctx: ExecContext) -> str:
    """Ensure the comments overlay is open; return the current dump XML."""
    xml = Path(ctx.ui.dump()["path"]).read_text()
    if _parse_comment_rows(xml):
        return xml
    entry = ctx.ui.find_by_resource_id(xml, _COMMENT_BTN)
    if entry is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "comment entry not visible",
            hint="open a video detail first via `kuaishou open --rank N`",
        )
    ctx.input.tap_node(entry)
    time.sleep(2)
    return Path(ctx.ui.dump()["path"]).read_text()


def _compose_and_send(ctx: ExecContext, text: str, *, commit: bool) -> dict[str, Any]:
    """Type `text` into the comment/reply compose editor and (optionally) send.

    Assumes the compose editor has just been opened. CJK pre-swaps ADBKeyboard.
    Returns the result dict; restores IME in finally.
    """
    needs_cjk = not text.isascii()
    prev_ime = _ime.current_ime(ctx.device) if needs_cjk else None
    if needs_cjk:
        _ime.set_adbkeyboard(ctx.device)
        time.sleep(0.6)
    try:
        xml = Path(ctx.ui.dump()["path"]).read_text()
        inp = ctx.ui.find_by_resource_id(xml, _EDITOR) or find_first_by_class(xml, "EditText")
        if inp is None:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "compose input not visible",
                hint="tapping the comment / 回复 affordance did not open the compose box",
            )
        ctx.input.tap_node(inp)
        time.sleep(1.0)
        if needs_cjk:
            ctx.device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(text)}")
        else:
            ctx.input.type_text(text)
        time.sleep(1.5)

        xml = Path(ctx.ui.dump()["path"]).read_text()
        send_btn = ctx.ui.find_by_resource_id(xml, _FINISH_BTN) or ctx.ui.find_by_text(xml, "发送")
        if send_btn is None:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "send button did not appear",
                hint="text may not have been entered; check IME with `doctor`",
            )

        if not commit:
            ctx.input.keyevent("back")
            return {
                "dry_run": True,
                "committed": False,
                "send_button_cx": send_btn["cx"],
                "send_button_cy": send_btn["cy"],
            }

        ctx.input.tap_node(send_btn)
        time.sleep(4)
        xml = Path(ctx.ui.dump()["path"]).read_text()
        return {"dry_run": False, "committed": True, "verified_visible": text in xml}
    finally:
        if needs_cjk and prev_ime:
            _ime.restore_ime(ctx.device, prev_ime)


# ----- comment -----------------------------------------------------------------


def _comment_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--text", required=True)


@app.verb("comment", add_args=_comment_args, requires_commit_flag=True)
def comment(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Post a top-level comment on the current video.

    Default = dry-run (open compose, type, locate send, cancel). --commit sends.
    """
    ctx.linter.check_or_raise(args.text)
    ctx.governor.check_or_raise("comment")
    _disable_animations(ctx)

    xml = _open_comments(ctx)
    # Tap the inline compose bar ("发条有爱评论~") to bring up the editor.
    bar = ctx.ui.find_by_resource_id(xml, _EDITOR)
    if bar is None:
        from mobilecli.core.ui import find_by_content_desc_contains

        bar = find_by_content_desc_contains(xml, "评论框") or ctx.ui.find_by_text(xml, "发条有爱评论~")
    if bar is not None:
        ctx.input.tap_node(bar)
        time.sleep(1.2)

    result = _compose_and_send(ctx, args.text, commit=getattr(args, "commit", False))
    result["text"] = args.text
    if result.get("committed"):
        ctx.governor.record("comment")
    return result


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
    _disable_animations(ctx)

    xml = _open_comments(ctx)
    rows = _parse_comment_rows(xml)
    if not rows:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "no comments visible",
            hint="open a video detail first via `kuaishou open --rank N`",
        )
    target = select_comment(rows, rank=args.rank, match=args.match)

    ctx.input.tap_node(target.reply_node)  # opens compose targeted at that comment
    time.sleep(1.5)

    result = _compose_and_send(ctx, args.text, commit=getattr(args, "commit", False))
    result["text"] = args.text
    result["target_index"] = target.index
    result["target_text"] = target.text
    if result.get("committed"):
        ctx.governor.record("comment")
    return result


# ----- profile -----------------------------------------------------------------


_ME_TAB_XY = (972, 2283)  # 快手底部导航 "我"


def _profile_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--avatar-out", default=None, help="头像 PNG 落盘路径")


@app.verb("profile", add_args=_profile_args)
def profile(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """读取快手登录态;已登录则返回头像(裁剪PNG)/昵称/快手号/关注·粉丝·获赞数/简介。"""
    _ensure_home(ctx)
    ctx.input.tap_xy(*_ME_TAB_XY)
    time.sleep(2.5)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    info = _parse_kuaishou_profile(xml)
    if not info.get("logged_in"):
        return {"logged_in": False}
    bounds = info.pop("avatar_bounds", None)
    if bounds is not None:
        info["avatar"] = ctx.ui.screenshot_region(bounds, args.avatar_out)["path"]
    else:
        info["avatar"] = None
    return info
