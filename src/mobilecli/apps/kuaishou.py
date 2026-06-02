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
from mobilecli.apps._publish import (
    classify_media,
    order_media_for_cover,
    parse_tags,
    resolve_cover,
)
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
        # docs/anti-risk-control.md 暂无快手专列;保守取 5(对齐抖音作品 2–5/天)。
        # TODO: 在 anti-risk-control.md 补一行快手 posts 后以文档为准(plugin-guide 要求)。
        "publish": 5,
    },
    extra_lint_patterns=[],
)

_HOME_ACTIVITY_SUFFIX = ".HomeActivity"
_SEARCH_BTN = "com.smile.gifmaker:id/search_btn"
_EDITOR = "com.smile.gifmaker:id/editor"
_PLAY_CONTAINER = "com.smile.gifmaker:id/play_view_container"
_SEARCH_CARD = "com.smile.gifmaker:id/container"  # 新版搜索页结果卡(可点 + 卡片尺寸过滤)
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


def _result_cards(xml: str) -> list[dict[str, Any]]:
    """搜索结果卡片节点(文档顺序)。

    新版搜索页:可点的 id/container,按卡片尺寸过滤(宽>100、高>200,排除细条/全宽头部);
    旧版回退 play_view_container(按宽度过滤掉边角碎块)。
    """
    cards = [
        c
        for c in find_all_by_resource_id(xml, _SEARCH_CARD)
        if c.get("clickable")
        and c["bounds"]
        and (c["bounds"][2] - c["bounds"][0]) > 100
        and (c["bounds"][3] - c["bounds"][1]) > 200
    ]
    if not cards:
        cards = [
            c
            for c in find_all_by_resource_id(xml, _PLAY_CONTAINER)
            if c["bounds"] and (c["bounds"][2] - c["bounds"][0]) > 100
        ]
    return cards


def _disable_animations(ctx: ExecContext) -> None:
    """Zero the global animation scales so uiautomator dump can reach idle.

    Required for Kuaishou's autoplaying detail / overlay screens. Persists on
    the device (benign for an automation device)."""
    for key in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
        try:
            ctx.device.shell(f"settings put global {key} 0")
        except EmError:
            pass


# 弹窗 / 开屏广告 / 插屏广告的关闭控件关键词(text 或 content-desc 精确命中其一)。
# 只点已识别的关闭控件,绝不乱点空白 —— 避免误触把广告点开、跳转到落地页。
_POPUP_CLOSE_LABELS = (
    "忽略",
    "跳过",
    "关闭",
    "我知道了",
    "知道了",
    "以后再说",
    "暂不更新",
    "暂不",
    "稍后再说",
    "取消",
    "不感兴趣",
)
_POPUP_CLOSE_DESCS = ("关闭", "跳过", "关闭广告", "关闭按钮", "关闭弹窗")


def _find_popup_close(ctx: ExecContext, xml: str) -> dict[str, Any] | None:
    """找弹窗/广告的关闭控件;找不到返回 None(则不点任何东西)。

    text 精确命中优先(忽略/跳过/关闭…),其次 content-desc(图标类关闭按钮无文字)。
    """
    for label in _POPUP_CLOSE_LABELS:
        node = ctx.ui.find_by_text(xml, label)
        if node is not None:
            return node
    for desc in _POPUP_CLOSE_DESCS:
        node = ctx.ui.find_by_content_desc(xml, desc)
        if node is not None:
            return node
    return None


def _dismiss_popups(ctx: ExecContext, max_rounds: int = 4) -> list[str]:
    """逐轮关闭插屏/开屏广告/系统弹窗(忽略/跳过/关闭/我知道了…),返回点掉的标签列表。

    只点已识别的关闭控件,绝不乱点空白(避免误触把广告点开)。一轮找不到即停。
    """
    closed: list[str] = []
    for _ in range(max_rounds):
        try:
            xml = Path(ctx.ui.dump()["path"]).read_text()
        except EmError:
            break
        node = _find_popup_close(ctx, xml)
        if node is None:
            break
        label = (node.get("text") or node.get("content_desc") or "?").strip()
        ctx.input.tap_node(node)
        closed.append(label)
        time.sleep(1.0)
    return closed


def _on_home(ctx: ExecContext) -> bool:
    return str(ctx.app.foreground().get("activity", "")).endswith(_HOME_ACTIVITY_SUFFIX)


def _ensure_home(ctx: ExecContext) -> dict[str, Any]:
    """Force Kuaishou to the 首页 feed (where the 查找 search entry lives).

    返回 {"foreground", "dismissed"};dismissed 为本次关掉的弹窗/广告标签列表。
    """
    ctx.app.ensure_foreground()
    time.sleep(0.5)
    _disable_animations(ctx)
    dismissed = _dismiss_popups(ctx)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    home_tab = ctx.ui.find_by_content_desc(xml, "首页")
    if home_tab is not None:
        ctx.input.tap_node(home_tab)
        time.sleep(1.5)
        dismissed += _dismiss_popups(ctx)  # 切首页后可能再弹一波(活动/广告),再清一轮
    return {"foreground": ctx.app.foreground(), "dismissed": dismissed}


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
    """Launch Kuaishou, disable animation scales, clear popups/ads, go to 首页 feed."""
    res = _ensure_home(ctx)
    return {
        "foreground": res["foreground"],
        "package": PACKAGE,
        "on_home": _on_home(ctx),
        "dismissed_popups": res["dismissed"],
    }


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
    # _EDITOR(id/editor)会随版本漂移,回退首个 EditText(同 comment/reply 套路)。
    inp = ctx.ui.find_by_resource_id(xml, _EDITOR) or find_first_by_class(xml, "EditText")
    if inp is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "kuaishou search input not found",
            hint="resource-id 可能漂移;`mobilecli screenshot` 看搜索页",
        )

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
    cards = _result_cards(xml)
    results = [
        {"index": i, "cx": c["cx"], "cy": c["cy"], "bounds": c["bounds"]}
        for i, c in enumerate(cards[: args.limit], 1)
    ]
    return {"keyword": args.keyword, "results": results}


# ----- open --------------------------------------------------------------------


def _open_args(p: argparse.ArgumentParser) -> None:
    # 优先 --cx/--cy:直接点 search 返回的坐标,最稳(搜索页状态多变,重新 dump 找卡
    # 偶发抓不到)。--rank 作回退:重新 dump 找第 N 张卡片。
    p.add_argument("--cx", type=int, default=None, help="直接点击的 X 坐标(用 search 返回的 cx)")
    p.add_argument("--cy", type=int, default=None, help="直接点击的 Y 坐标(用 search 返回的 cy)")
    p.add_argument("--rank", type=int, default=None, help="回退:点第 N 个结果(重新 dump 找卡)")


@app.verb("open", add_args=_open_args)
def open_result(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """点开搜索结果卡片。

    优先 --cx/--cy:直接点击 `search` 已返回的坐标,最稳(搜索页状态多变,重新 dump
    找卡偶发抓不到)。否则 --rank:重新 dump 找第 N 张卡片(回退路径)。
    """
    if args.cx is not None and args.cy is not None:
        ctx.input.tap_xy(args.cx, args.cy)
        chosen: dict[str, Any] = {"tapped": "xy", "cx": args.cx, "cy": args.cy}
    elif args.rank is not None:
        xml = Path(ctx.ui.dump()["path"]).read_text()
        cards = _result_cards(xml)
        if args.rank < 1 or args.rank > len(cards):
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                f"rank {args.rank} out of range (have {len(cards)} cards)",
                hint="改用 --cx/--cy(传 search 返回的坐标,更稳),或先 `kuaishou search`",
            )
        card = cards[args.rank - 1]
        ctx.input.tap_node(card)
        chosen = {"tapped": "rank", "rank": args.rank, "cx": card["cx"], "cy": card["cy"]}
    else:
        raise EmError(
            ErrorCode.INVALID_ARG,
            "open 需要 --cx/--cy 或 --rank",
            hint="优先用 search 返回的坐标:`kuaishou open --cx <cx> --cy <cy>`",
        )
    time.sleep(3)
    _disable_animations(ctx)
    ctx.input.idle_browse()
    return {**chosen, "foreground": ctx.app.foreground()}


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

        bar = find_by_content_desc_contains(xml, "评论框") or ctx.ui.find_by_text(
            xml, "发条有爱评论~"
        )
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
    # 用 content-desc「我」定位底栏 tab,比硬坐标稳:"开启通知"等提示可能盖住硬坐标、
    # 误点进系统设置(假阴性根因)。失败则清弹窗回首页重试。
    info: dict[str, Any] = {"logged_in": False}
    for _ in range(3):
        xml = Path(ctx.ui.dump()["path"]).read_text()
        me = ctx.ui.find_by_content_desc(xml, "我")
        if me is not None:
            ctx.input.tap_node(me)
        else:
            ctx.input.tap_xy(*_ME_TAB_XY)
        time.sleep(2.5)
        info = _parse_kuaishou_profile(Path(ctx.ui.dump()["path"]).read_text())
        if info.get("logged_in"):
            break
        _dismiss_popups(ctx)
        _ensure_home(ctx)
    if not info.get("logged_in"):
        return {"logged_in": False}
    bounds = info.pop("avatar_bounds", None)
    if bounds is not None:
        info["avatar"] = ctx.ui.screenshot_region(bounds, args.avatar_out)["path"]
    else:
        info["avatar"] = None
    return info


# ----- publish (research/ui-trees/kuaishou/00-selectors-publish.md — 待 recon) --
#
# 发布流的入口/选素材/编辑/撰写/声明/发布 selector 全部为 TODO(recon):真机 dump
# 后填 _PUB / _DECLARE_TEXT。步骤顺序照 xiaohongshu.publish 的成熟流程作先验;
# 快手实际步数/弹窗可能不同,recon 时校正。纯逻辑(判型/标签/封面)已走 _publish。

_DECLARE_CHOICES = ["none", "original", "ai", "reprint"]

_PUB: dict[str, Any] = {
    "post_entry_desc": "TODO_发布入口",  # TODO(recon): 底部"＋"/拍摄 的 content-desc
    "album_entry_text": "TODO_相册",  # TODO(recon): 进相册/图文 入口文案
    "select_cell": "com.smile.gifmaker:id/TODO_select_cell",
    "go_next": "com.smile.gifmaker:id/TODO_go_next",
    "edit_next": "com.smile.gifmaker:id/TODO_edit_next",
    "title": "com.smile.gifmaker:id/TODO_title",
    "body": "com.smile.gifmaker:id/TODO_body",
    "declare_entry_text": "TODO_内容自主声明",
    "publish_btn": "com.smile.gifmaker:id/TODO_publish",
    "no_perm_text": "去开启权限",
}

_DECLARE_TEXT = {
    # TODO(recon): 快手发布页「作品声明 / 内容自主声明」各项真实中文文案。
    "original": "TODO_原创",
    "ai": "TODO_AI生成内容",
    "reprint": "TODO_转载",
}


def _need(node: dict[str, Any] | None, what: str) -> dict[str, Any]:
    """selector 命中守卫:未找到(含 TODO 占位)抛带 hint 的 ELEMENT_NOT_FOUND。"""
    if node is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            f"{what} 未找到(selector 待 recon 填)",
            hint="真机 dump 后在 kuaishou._PUB / _DECLARE_TEXT 补 selector;"
            "见 research/ui-trees/kuaishou/00-selectors-publish.md",
        )
    return node


def _type_cjk(ctx: ExecContext, node: dict[str, Any], text: str) -> None:
    """点输入框 + 输入 + 回查重试。CJK 切 ADBKeyboard,末尾 restore(避免 compose 掉焦)。"""
    needs_cjk = not text.isascii()
    prev = _ime.current_ime(ctx.device) if needs_cjk else None
    if needs_cjk:
        _ime.set_adbkeyboard(ctx.device)
        time.sleep(0.6)
    try:
        ctx.input.tap_node(node)
        time.sleep(1.0)
        for _attempt in range(2):  # ADBKeyboard 偶发丢广播:回查前6字符未中则重试
            if needs_cjk:
                ctx.device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(text)}")
            else:
                ctx.input.type_text(text)
            time.sleep(1.2)
            if text[:6] in Path(ctx.ui.dump()["path"]).read_text():
                return
    finally:
        if needs_cjk and prev:
            _ime.restore_ime(ctx.device, prev)


def _set_declare(ctx: ExecContext, declare: str, commit: bool) -> bool:
    """进入「内容自主声明」选对应项,返回是否真的选中。

    commit 模式下入口/选项缺失(含 TODO 占位)抛 ELEMENT_NOT_FOUND——避免谎报已设;
    dry-run 下缺失则跳过返回 False。
    """
    if declare == "none":
        return False
    label = _DECLARE_TEXT.get(declare)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    entry = ctx.ui.find_by_text(xml, _PUB["declare_entry_text"])
    if entry is None:
        if commit:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "声明入口未找到(selector 待 recon)",
                hint="真机 dump 后补 kuaishou._PUB['declare_entry_text']",
            )
        return False
    ctx.input.tap_node(entry)
    time.sleep(1.5)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    opt = ctx.ui.find_by_text(xml, label) if label else None
    if opt is None:
        if commit:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                f"声明选项 '{declare}' 未找到(selector 待 recon)",
                hint="真机 dump 后补 kuaishou._DECLARE_TEXT",
            )
        ctx.input.keyevent("back")
        time.sleep(1.0)
        return False
    ctx.input.tap_node(opt)
    time.sleep(0.8)
    ctx.input.keyevent("back")
    time.sleep(1.0)
    return True


def _publish_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--media", nargs="+", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--tags", default=None)
    p.add_argument("--cover", default=None, help="图文: 第N张(int); 视频: 封面图路径")
    p.add_argument("--declare", default="none", choices=_DECLARE_CHOICES)


@app.verb("publish", add_args=_publish_args, requires_commit_flag=True)
def publish(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """发布图文/视频(标题/正文/话题/自主声明)。默认 dry-run(走到发布键前停);--commit 真发。

    快手发布流 selector 为 TODO(recon):真机 dump 前只能跑到推素材/进发布页,
    遇到未填 selector 会抛 ELEMENT_NOT_FOUND。纯逻辑(判型/标签/封面)已共享 _publish。
    """
    # 1. lint + 判型 + cover 校验(纯逻辑,真实可跑)
    ctx.linter.check_or_raise(args.title)
    ctx.linter.check_or_raise(args.body)
    tags = parse_tags(args.tags)
    for t in tags:
        ctx.linter.check_or_raise(t)
    media_type = classify_media(args.media)
    cover_index, cover_path = resolve_cover(media_type, args.cover)

    # 2. 推素材(图文按封面顺序;cover_path 一并推)
    media = args.media
    if media_type == "image":
        media = order_media_for_cover(media, cover_index)
    to_push = list(media) + ([cover_path] if cover_path else [])
    pushed = ctx.media.push_to_gallery(to_push)

    commit = getattr(args, "commit", False)
    if commit:
        ctx.governor.check_or_raise("publish")
    steps: list[str] = [f"pushed {pushed['count']} media ({media_type})"]

    # 3. 进发布入口(selector 待 recon)
    _ensure_home(ctx)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    entry = _need(ctx.ui.find_by_content_desc(xml, _PUB["post_entry_desc"]), "发布入口")
    ctx.input.tap_node(entry)
    time.sleep(2)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    if _PUB["no_perm_text"] in xml:
        raise EmError(
            ErrorCode.PERMISSION_REQUIRED,
            "快手无完整相册权限,无法读取推入素材",
            hint="adb shell pm grant com.smile.gifmaker android.permission.READ_MEDIA_IMAGES "
            "&& ...READ_MEDIA_VIDEO",
        )
    album = _need(ctx.ui.find_by_text(xml, _PUB["album_entry_text"]), "相册入口")
    ctx.input.tap_node(album)
    time.sleep(3)
    steps.append("opened album")

    # 4. 选前 len(media) 个素材
    xml = Path(ctx.ui.dump()["path"]).read_text()
    cells = ctx.ui.find_all_by_resource_id(xml, _PUB["select_cell"])
    if len(cells) < len(media):
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            f"album shows {len(cells)} selectable items, need {len(media)} (selector 待 recon)",
            hint="检查 READ_MEDIA 权限 / kuaishou._PUB['select_cell']",
        )
    for i in range(len(media)):
        ctx.input.tap_node(cells[i])
        time.sleep(0.6)
    go = _need(
        ctx.ui.find_by_resource_id(Path(ctx.ui.dump()["path"]).read_text(), _PUB["go_next"]),
        "下一步",
    )
    ctx.input.tap_node(go)
    time.sleep(3)
    steps.append(f"selected {len(media)} item(s)")

    # 5. 编辑页 -> 下一步到发布编辑页(若有)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    edit_next = ctx.ui.find_by_resource_id(xml, _PUB["edit_next"])
    if edit_next is not None:
        ctx.input.tap_node(edit_next)
        time.sleep(3)
        steps.append("passed edit page")

    # 6. 标题 + 正文
    xml = Path(ctx.ui.dump()["path"]).read_text()
    title_node = _need(ctx.ui.find_by_resource_id(xml, _PUB["title"]), "标题输入框")
    _type_cjk(ctx, title_node, args.title)
    body_node = _need(
        ctx.ui.find_by_resource_id(Path(ctx.ui.dump()["path"]).read_text(), _PUB["body"]),
        "正文输入框",
    )
    _type_cjk(ctx, body_node, args.body)
    steps.append("filled title+body")

    # 7. 话题(快手常把 #tag 打进正文;精确话题联想待 recon)
    if tags:
        steps.append(f"tags={tags} (linking 待 recon)")

    # 8. 自主声明
    if args.declare != "none":
        applied = _set_declare(ctx, args.declare, commit)
        steps.append(f"declare={args.declare}" + ("" if applied else "(未应用,待recon)"))

    # 9. 收键盘 + 定位发布键
    ctx.input.keyevent("back")
    time.sleep(1.0)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    pub_btn = _need(ctx.ui.find_by_resource_id(xml, _PUB["publish_btn"]), "发布键")
    shot = ctx.ui.screenshot()["path"]
    steps.append("reached 发布")

    base = {
        "media_type": media_type,
        "pushed": pushed["pushed"],
        "title": args.title,
        "body_len": len(args.body),
        "tags": tags,
        "cover": (
            f"index:{cover_index}"
            if cover_index
            else f"path:{cover_path}"
            if cover_path
            else "default"
        ),
        "declare": args.declare,
        "steps": steps,
        "screenshot": shot,
        "publish_button_cx": pub_btn["cx"],
        "publish_button_cy": pub_btn["cy"],
    }
    if not commit:
        ctx.app.force_stop()  # 放弃草稿(不存不发)
        return {"dry_run": True, "committed": False, **base}

    ctx.input.tap_node(pub_btn)
    time.sleep(5)
    verified = _on_home(ctx)
    ctx.governor.record("publish")
    return {"dry_run": False, "committed": True, "verified_published": verified, **base}
