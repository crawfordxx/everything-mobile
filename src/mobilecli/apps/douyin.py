"""Douyin app plugin (抖音). Selectors per research/ui-trees/douyin/00-selectors.md."""

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
    find_all_by_content_desc_contains,
    find_all_by_resource_id,
    find_by_content_desc,
    find_by_content_desc_contains,
    find_by_resource_id,
    find_by_text_contains,
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
        # docs/anti-risk-control.md: 抖音作品 2–5/天(前 3 天 0),取保守上限 5。
        "publish": 5,
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


def _disable_animations(ctx: ExecContext) -> None:
    """关全局动画缩放,减少过渡动画导致的 uiautomator dump 取不到 idle。

    注:对「图片编辑页自动拼成的带音乐循环幻灯片」这种媒体播放无效(那是播放不是
    过渡动画),发布流靠 dump 失败时的坐标兜底前进处理(见 publish 第6步)。
    """
    for key in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
        try:
            ctx.device.shell(f"settings put global {key} 0")
        except EmError:
            pass


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
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
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
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
    inp = ctx.ui.find_by_resource_id(xml, "com.ss.android.ugc.aweme:id/et_search_kw")
    if inp is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "search input not found")
    # 统一走 ADBKeyboard 清空+输入(中英文都生效):此前 type_text 不清空、且打不了中文,
    # 残留词会被一起搜(搜「AI」命中上次的「护肤」)。clear_and_input 内部 focus→清空→输入。
    _ime.clear_and_input(ctx.device, args.keyword, lambda: ctx.input.tap_node(inp))
    ctx.input.keyevent(66)  # KEYCODE_ENTER
    time.sleep(3)

    # 3. Parse result cards (resource-id q21)
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
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
    # 优先 --cx/--cy:直接点 search 返回的坐标,最稳(抖音搜索页状态多变,重新 dump
    # 找卡偶发抓不到)。--rank 作回退:重新 dump 找第 N 张卡片。
    p.add_argument("--cx", type=int, default=None, help="直接点击的 X 坐标(用 search 返回的 cx)")
    p.add_argument("--cy", type=int, default=None, help="直接点击的 Y 坐标(用 search 返回的 cy)")
    p.add_argument("--rank", type=int, default=None, help="回退:点第 N 个结果(重新 dump 找卡)")


@app.verb("open", add_args=_open_args)
def open_result(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """点开搜索结果卡片。

    优先 --cx/--cy:直接点击 `search` 已返回的坐标,最稳(抖音搜索页状态多变,重新
    dump 找卡偶发抓不到)。否则 --rank:重新 dump 找第 N 张卡片(回退路径)。
    """
    if args.cx is not None and args.cy is not None:
        ctx.input.tap_xy(args.cx, args.cy)
        chosen: dict[str, Any] = {"tapped": "xy", "cx": args.cx, "cy": args.cy}
    elif args.rank is not None:
        xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
        cards = ctx.ui.find_all_by_resource_id(xml, "com.ss.android.ugc.aweme:id/q21")
        if args.rank < 1 or args.rank > len(cards):
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                f"rank {args.rank} out of range (have {len(cards)} cards)",
                hint="改用 --cx/--cy(传 search 返回的坐标,更稳),或先 `douyin search`",
            )
        card = cards[args.rank - 1]
        ctx.input.tap_node(card)
        chosen = {"tapped": "rank", "rank": args.rank, "cx": card["cx"], "cy": card["cy"]}
    else:
        raise EmError(
            ErrorCode.INVALID_ARG,
            "open 需要 --cx/--cy 或 --rank",
            hint="优先用 search 返回的坐标:`douyin open --cx <cx> --cy <cy>`",
        )
    time.sleep(3)

    # Switch to single-column for stable comment access
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
    toggle = ctx.ui.find_by_content_desc(xml, "单双列切换图标")
    if toggle is not None:
        ctx.input.tap_node(toggle)
        time.sleep(2)
    ctx.input.idle_browse()
    return {**chosen, "foreground": ctx.app.foreground()}


# ----- detail ------------------------------------------------------------------

_COUNT_RE = re.compile(r"(\d+(?:\.\d+)?[万亿]?)")


def _parse_count(s: str) -> str:
    m = _COUNT_RE.search(s or "")
    return m.group(1) if m else ""


@app.verb("detail")
def detail(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Read like / comment / share / collect counts from the current video detail."""
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
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
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
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

    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
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
# 评论输入框 id 会随抖音版本漂移;以此为主选择器,实际命中靠「id 或首个 EditText」双保险。
_COMMENT_INPUT_ID = "com.ss.android.ugc.aweme:id/eoy"


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

    # 找评论入口:详情页底部内联评论条(eoy/EditText);若未显示则点「评论」图标展开。
    # eoy 会随版本漂移,故回退首个 EditText。
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
    entry = ctx.ui.find_by_resource_id(xml, _COMMENT_INPUT_ID) or find_first_by_class(
        xml, "EditText"
    )
    if entry is None:
        cmt = find_by_content_desc_contains(xml, "评论", "按钮")
        if cmt is None:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "comment input/entry not visible",
                hint="open a video / photo detail first via `douyin open`",
            )
        ctx.input.tap_node(cmt)
        time.sleep(2)
        xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
        entry = ctx.ui.find_by_resource_id(xml, _COMMENT_INPUT_ID) or find_first_by_class(
            xml, "EditText"
        )
        if entry is None:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "comment entry not visible after opening panel",
                hint="resource-id 可能漂移;`mobilecli screenshot` 看当前态",
            )

    # CJK 关键:点评论条会弹出 compose 浮层;输入时若再切 IME 会把浮层挤掉焦(=发送键
    # 永不出现)。照 reply:开 compose 前就先切好 ADBKeyboard,中途直接 broadcast,用完
    # 在 finally 里 restore。ASCII 无需切 IME,走 type_text。
    needs_cjk = not args.text.isascii()
    prev_ime = _ime.current_ime(ctx.device) if needs_cjk else None
    if needs_cjk:
        _ime.set_adbkeyboard(ctx.device)
        time.sleep(0.6)
    try:
        ctx.input.tap_node(entry)  # 点评论条,弹出 compose 并聚焦输入
        time.sleep(1.5)
        if needs_cjk:
            ctx.device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(args.text)}")
        else:
            ctx.input.type_text(args.text)
        time.sleep(1.5)

        xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
        # 发送键 id(es1)会漂移:优先稳定文案「发送」(与 reply 一致),回退 es1。
        send_btn = ctx.ui.find_by_text(xml, "发送") or ctx.ui.find_by_resource_id(
            xml, "com.ss.android.ugc.aweme:id/es1"
        )
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
        xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
        verified = args.text in xml
        ctx.governor.record("comment")
        return {
            "dry_run": False,
            "committed": True,
            "verified_visible": verified,
            "text": args.text,
        }
    finally:
        if needs_cjk and prev_ime:
            _ime.restore_ime(ctx.device, prev_ime)


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
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
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
        xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
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

        xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
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

        xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
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
        xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
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
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
    info = _parse_douyin_profile(xml)
    if not info.get("logged_in"):
        return {"logged_in": False}
    bounds = info.pop("avatar_bounds", None)
    if bounds is not None:
        info["avatar"] = ctx.ui.screenshot_region(bounds, args.avatar_out)["path"]
    else:
        info["avatar"] = None
    return info


# ----- publish (真机 recon 2026-06-02:抖音图文发布流) ---------------------------
#
# 真实流程:首页拍摄 → 相机页相册 → [系统相册权限「全部允许」] → 选择圈(content-desc
# 含「未选中」)→ 下一步(相册)→ 下一步(编辑页;循环至发布页出现「发作品」)→
# 发布页:添加标题 / 添加作品描述 / 添加自主声明 / 发作品。
# 注:自主声明子页各选项文案尚未 recon,_set_declare 为 best-effort(--declare none 不受影响)。

_DECLARE_CHOICES = ["none", "original", "ai", "reprint"]

_PUB: dict[str, str] = {
    "post_entry": "拍摄",  # 首页底部 content-desc「拍摄，按钮」
    "album_entry": "相册",  # 相机页 content-desc「相册」
    "perm_allow": "全部允许",  # 系统相册权限框(首次)
    "next": "下一步",  # 相册下一步 / 编辑页下一步(同文案,循环至发布页)
    "select_unsel": "未选中",  # 选择圈 content-desc「, 未选中」
    "title_id": "com.ss.android.ugc.aweme:id/id7",  # 标题 EditText
    "title_ph": "添加标题",
    "body_id": "com.ss.android.ugc.aweme:id/h2q",  # 作品描述 EditText
    "body_ph": "添加作品描述...",
    "declare_entry": "添加自主声明",  # content-desc(含全角逗号,用 contains)
    "publish_btn": "发作品",
    "keep_draft": "存草稿",  # 未完成草稿弹窗「继续编辑作品吗？」的「存草稿」
}

_DECLARE_TEXT = {
    # TODO(recon): 抖音「内容自主声明」子页各项真实文案(原创 / AI生成 / 转载…)。
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
            hint="真机 dump 后在 douyin._PUB / _DECLARE_TEXT 补 selector;"
            "见 research/ui-trees/douyin/00-selectors-publish.md",
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
            if text[:6] in Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8"):
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
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
    entry = find_by_content_desc_contains(xml, _PUB["declare_entry"])
    if entry is None:
        if commit:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "声明入口未找到",
                hint="真机 dump 后补 douyin._PUB['declare_entry']",
            )
        return False
    ctx.input.tap_node(entry)
    time.sleep(1.5)
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
    opt = ctx.ui.find_by_text(xml, label) if label else None
    if opt is None:
        if commit:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                f"声明选项 '{declare}' 未找到(selector 待 recon)",
                hint="真机 dump 后补 douyin._DECLARE_TEXT",
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

    抖音发布流 selector 为 TODO(recon):真机 dump 前只能跑到推素材/进发布页,
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

    # 3. 首页 → 拍摄 → 相机页 → 相册。首页 feed 自动播放 + 残留草稿弹窗都会干扰,循环处理:
    #    残留草稿会弹「继续编辑作品吗？」盖住底栏 → 先点「存草稿」存盘回首页,下轮再找拍摄。
    _ensure_home(ctx)
    _disable_animations(ctx)
    entry = None
    for _ in range(5):
        time.sleep(1.5)
        try:
            xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
        except EmError:
            continue
        keep = ctx.ui.find_by_text(xml, _PUB["keep_draft"])
        if keep is not None:
            ctx.input.tap_node(keep)
            time.sleep(2)
            continue
        entry = find_by_content_desc_contains(xml, _PUB["post_entry"])
        if entry is not None:
            break
    ctx.input.tap_node(_need(entry, "拍摄入口"))
    time.sleep(2.5)

    # tap 拍摄 后仍可能弹草稿框(进行中草稿):存草稿后重新进拍摄起新作品。
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
    keep = ctx.ui.find_by_text(xml, _PUB["keep_draft"])
    if keep is not None:
        ctx.input.tap_node(keep)
        time.sleep(2)
        re_entry = find_by_content_desc_contains(
            Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8"), _PUB["post_entry"]
        )
        ctx.input.tap_node(_need(re_entry, "拍摄入口(草稿后)"))
        time.sleep(2.5)

    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
    album = _need(ctx.ui.find_by_content_desc(xml, _PUB["album_entry"]), "相册入口")
    ctx.input.tap_node(album)
    time.sleep(3)

    # 4. 系统相册权限框(首次出现则「全部允许」)
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
    allow = ctx.ui.find_by_text(xml, _PUB["perm_allow"])
    if allow is not None:
        ctx.input.tap_node(allow)
        time.sleep(2.5)
    steps.append("opened album")

    # 5. 选前 N 个素材:点 content-desc 含「未选中」的选择圈(推入素材排在最前)
    for n in range(len(media)):
        xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
        circles = find_all_by_content_desc_contains(xml, _PUB["select_unsel"])
        if not circles:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                f"相册无更多可选素材({n}/{len(media)} 已选)",
                hint="检查 READ_MEDIA 权限 / 素材是否已推入相册",
            )
        ctx.input.tap_node(circles[0])
        time.sleep(0.8)
    steps.append(f"selected {len(media)} item(s)")

    # 6. 下一步(相册)→ 编辑页 → … 循环至发布页(出现「发作品」)。
    #    抖音多图编辑页会自动拼成带音乐的循环幻灯片、持续播放 → uiautomator dump 取不到
    #    idle 而失败;此时按上一次「下一步」的坐标兜底前进(相册/编辑页的下一步同在右下)。
    last_next: tuple[int, int] | None = None
    for _ in range(5):
        try:
            xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
        except EmError:
            if last_next is None:
                raise
            ctx.input.tap_xy(*last_next)
            time.sleep(3)
            continue
        if ctx.ui.find_by_text(xml, _PUB["publish_btn"]) is not None:
            break
        nxt = find_by_text_contains(xml, _PUB["next"])  # 「下一步」或「下一步 (2)」
        if nxt is None:
            break
        last_next = (nxt["cx"], nxt["cy"])
        ctx.input.tap_node(nxt)
        time.sleep(3)
    steps.append("reached compose page")

    # 7. 文案。抖音图文「添加标题」「添加作品描述」两个 EditText 在此 build 上焦点联动,
    #    程序化分别聚焦不稳(正文会被打进标题框);统一把 标题+正文(+#话题)作为整段
    #    文案打进文案框(抖音文案本就常是一整段)。CJK 安全:_type_cjk 先切 ADBKeyboard。
    caption = args.title
    if args.body:
        # 用空格而非换行:换行会让 _type_cjk 的回查(text[:6] in dump)失配而重复广播。
        caption = f"{caption} {args.body}" if caption else args.body
    if tags:
        caption += "".join(f" #{t}" for t in tags)
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
    cap_node = _need(
        ctx.ui.find_by_resource_id(xml, _PUB["title_id"])
        or ctx.ui.find_by_text(xml, _PUB["title_ph"])
        or ctx.ui.find_by_resource_id(xml, _PUB["body_id"])
        or ctx.ui.find_by_text(xml, _PUB["body_ph"]),
        "文案输入框",
    )
    _type_cjk(ctx, cap_node, caption)
    steps.append("filled caption" + (f" +tags{tags}" if tags else ""))

    # 8. 自主声明(best-effort:子页文案待 recon)
    if args.declare != "none":
        applied = _set_declare(ctx, args.declare, commit)
        steps.append(f"declare={args.declare}" + ("" if applied else "(未应用,待recon)"))

    # 9. 收键盘 + 定位发布键(发作品)
    ctx.input.keyevent("back")
    time.sleep(1.0)
    xml = Path(ctx.ui.dump()["path"]).read_text(encoding="utf-8")
    pub_btn = _need(ctx.ui.find_by_text(xml, _PUB["publish_btn"]), "发布键(发作品)")
    shot = ctx.ui.screenshot()["path"]
    steps.append("reached 发作品")

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
