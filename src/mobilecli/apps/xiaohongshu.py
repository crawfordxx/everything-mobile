"""Xiaohongshu app plugin (小红书).

Selectors per research/ui-trees/xiaohongshu/00-selectors.md.

Mutating verbs (`like`, `comment`) follow the standard --commit gate (mirrors
douyin): default path is dry-run; `--commit` plus `EM_ALLOW_COMMIT=1` actually
taps. Daily caps enforced via governor; text scanned by linter.
"""

from __future__ import annotations

import argparse
import re
import shlex
import time
from pathlib import Path
from typing import Any

from mobilecli.apps._comments import CommentRow, select_comment
from mobilecli.apps._publish import classify_media as _classify_media
from mobilecli.apps._publish import order_media_for_cover as _order_media_for_cover
from mobilecli.apps._publish import parse_tags as _parse_tags
from mobilecli.core import ime as _ime
from mobilecli.core.ui import find_all_by_resource_id, find_by_resource_id
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
        "publish": 3,
    },
    extra_lint_patterns=[],
)


# Home-state oracle (UI-tree research: home is IndexActivityV2).
_HOME_ACTIVITY_SUFFIX = ".IndexActivityV2"


_RESULT_CARD_IDS = (
    "com.xingin.xhs:id/searchNoteCard",  # legacy
    "com.xingin.xhs:id/resultNoteContainer",  # 2026+ GlobalSearchActivity
)


def _find_result_cards(ctx: ExecContext, xml: str) -> list[dict[str, Any]]:
    """Return all search-result note cards on screen, trying known id variants."""
    for rid in _RESULT_CARD_IDS:
        cards = ctx.ui.find_all_by_resource_id(xml, rid)
        if cards:
            return cards
    return []


def _first_edittext(xml: str) -> dict[str, Any] | None:
    """Find the first focusable EditText on the current screen (selector fallback)."""
    m = re.search(
        r'<node[^>]*class="android\.widget\.EditText"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*/?>',
        xml,
    )
    if m is None:
        return None
    x1, y1, x2, y2 = (int(g) for g in m.groups())
    return {
        "bounds": f"[{x1},{y1}][{x2},{y2}]",
        "cx": (x1 + x2) // 2,
        "cy": (y1 + y2) // 2,
        "text": "",
        "content_desc": "",
    }


_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([万亿]?)")


def _to_int(s: str) -> int:
    """'29' -> 29; '1.6万' -> 16000; content-desc '2关注' -> 2."""
    m = _NUM_RE.search(s or "")
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "万":
        val *= 10_000
    elif unit == "亿":
        val *= 100_000_000
    return int(val)


def _parse_profile(xml: str) -> dict[str, Any]:
    """Parse the 我/profile tab. logged_in oracle = nickname/iv_avatar present."""
    PFX = "com.xingin.xhs:id/"
    nick = find_by_resource_id(xml, PFX + "profile_new_page_avatar_card_nickname")
    avatar = find_by_resource_id(xml, PFX + "iv_avatar")
    if nick is None and avatar is None:
        return {"logged_in": False}

    redid = find_by_resource_id(xml, PFX + "profile_new_page_avatar_card_redid")
    ip = find_by_resource_id(xml, PFX + "profile_new_page_avatar_card_ip")
    bio = find_by_resource_id(xml, PFX + "userDescTv")
    follow = find_by_resource_id(xml, PFX + "follow_count")
    fans = find_by_resource_id(xml, PFX + "fans_count")
    fav = find_by_resource_id(xml, PFX + "fav_count")

    def _txt(node: dict[str, Any] | None) -> str:
        return (node.get("text") or "").strip() if node else ""

    red_txt = _txt(redid).replace("小红书号：", "").replace("小红书号:", "").strip()
    ip_txt = _txt(ip).replace("IP：", "").replace("IP:", "").strip()
    return {
        "logged_in": True,
        "nickname": _txt(nick),
        "red_id": red_txt,
        "ip": ip_txt,
        "follow_count": _to_int(_txt(follow)),
        "fans_count": _to_int(_txt(fans)),
        "fav_count": _to_int(_txt(fav)),
        "bio": _txt(bio),
        "avatar_bounds": tuple(avatar["bounds"]) if avatar else None,
    }


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
    search_node = None
    for rid in (
        "com.xingin.xhs:id/iv_search",
        "com.xingin.xhs:id/search",
        "com.xingin.xhs:id/mSearchToolBarSearchBtn",
    ):
        search_node = ctx.ui.find_by_resource_id(xml, rid)
        if search_node is not None:
            break
    if search_node is None:
        search_node = ctx.ui.find_by_content_desc(xml, "搜索")
    if search_node is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "XHS search affordance not found")
    ctx.input.tap_node(search_node)
    time.sleep(2)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    inp = None
    for rid in (
        "com.xingin.xhs:id/mSearchToolBarEt",
        "com.xingin.xhs:id/et_search",
        "com.xingin.xhs:id/search_edit",
    ):
        inp = ctx.ui.find_by_resource_id(xml, rid)
        if inp is not None:
            break
    if inp is None:
        inp = _first_edittext(xml)
    if inp is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "XHS search input not found")
    # IME + clear handling: XHS search input on this build has pre-filled
    # text ("搜索, ") plus a rotating trending-keyword hint ("拼多多v3怎么开"
    # etc). type_text only appends, so without an explicit clear we end up
    # either appending after "搜索, " or — if the broadcast doesn't land on
    # the focused field — letting XHS submit the hint as the default query.
    # That's why a user reported searching "扫地机器人" but landing on the
    # trending "石头P20 UP好价" results. Pre-swap to ADBKeyboard, focus, then
    # CLEAR_TEXT broadcast, then INPUT_TEXT, then Enter.
    needs_cjk = not args.keyword.isascii()
    prev_ime = _ime.current_ime(ctx.device) if needs_cjk else None
    if needs_cjk:
        _ime.set_adbkeyboard(ctx.device)
        time.sleep(0.6)

    try:
        ctx.input.tap_node(inp)
        time.sleep(0.8)
        # ADBKeyboard CLEAR_TEXT removes the existing text + escapes any
        # selection state. Safe on builds where the field is already empty.
        ctx.device.shell("am broadcast -a ADB_CLEAR_TEXT")
        time.sleep(0.4)
        if needs_cjk:
            ctx.device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(args.keyword)}")
        else:
            ctx.input.type_text(args.keyword)
        time.sleep(1.2)
        ctx.input.keyevent(66)
        time.sleep(3)
    finally:
        if needs_cjk and prev_ime:
            _ime.restore_ime(ctx.device, prev_ime)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    cards = _find_result_cards(ctx, xml)
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
    cards = _find_result_cards(ctx, xml)
    if args.rank < 1 or args.rank > len(cards):
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            f"rank {args.rank} out of range (have {len(cards)})",
        )
    ctx.input.tap_node(cards[args.rank - 1])
    time.sleep(3)
    ctx.input.idle_browse()
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
    ctx.input.reading_pause()
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


# ----- comments (shared parse for reply) ----------------------------------------

_TOPLEVEL_X_MAX = 180  # top-level comments start x≈149; sub-replies indent to x≈215
_TV_CONTENT_ID = "com.xingin.xhs:id/tv_content"
_TIME_REPLY_ID = "com.xingin.xhs:id/newTimePoiIpTransTv"


def _parse_comment_rows(xml: str) -> list[CommentRow]:
    """Parse top-level comment rows from the scrolled note-detail comments area.

    XHS stacks per comment: tv_user_name -> tv_content -> newTimePoiIpTransTv
    ("date region 回复"). Sub-replies live in subCommentLayout, indented to
    x≈215, and are excluded (x<180). Each top-level tv_content is paired with
    the nearest top-level time/reply line below it (the 回复 affordance).
    """
    contents = [
        n
        for n in find_all_by_resource_id(xml, _TV_CONTENT_ID)
        if n["bounds"] and n["bounds"][0] < _TOPLEVEL_X_MAX
    ]
    replies = [
        n
        for n in find_all_by_resource_id(xml, _TIME_REPLY_ID)
        if n["bounds"] and n["bounds"][0] < _TOPLEVEL_X_MAX
    ]
    rows: list[CommentRow] = []
    for content in contents:
        below = [r for r in replies if r["bounds"][1] >= content["bounds"][3]]
        if not below:
            continue  # partially-scrolled last row with no reply line visible
        reply_node = min(below, key=lambda r: r["bounds"][1])
        rows.append(
            CommentRow(
                index=len(rows) + 1,
                text=content["text"],
                reply_node=reply_node,
                content_node=content,  # fallback tap target if 回复 span miss
            )
        )
    return rows


# ----- like --------------------------------------------------------------------


@app.verb("like", requires_commit_flag=True)
def like(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Like the current note detail.

    Default = dry-run (locate like button, return coords).
    With --commit (and EM_ALLOW_COMMIT=1 gated by cli), actually tap.
    """
    ctx.governor.check_or_raise("like")

    xml = Path(ctx.ui.dump()["path"]).read_text()
    like_btn = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/noteLikeLayout")
    if like_btn is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "XHS like button not visible",
            hint="open a note detail first via `xiaohongshu open --rank N`",
        )

    before_desc = like_btn.get("content_desc", "")
    before_already_liked = "已赞" in before_desc

    if not getattr(args, "commit", False):
        return {
            "dry_run": True,
            "committed": False,
            "already_liked": before_already_liked,
            "like_button_cx": like_btn["cx"],
            "like_button_cy": like_btn["cy"],
        }

    ctx.input.tap_node(like_btn)
    time.sleep(1.5)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    after = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/noteLikeLayout")
    after_already_liked = "已赞" in (after.get("content_desc", "") if after else "")
    ctx.governor.record("like")
    return {
        "dry_run": False,
        "committed": True,
        "already_liked_before": before_already_liked,
        "already_liked_after": after_already_liked,
        "verified_changed": before_already_liked != after_already_liked,
    }


# ----- comment -----------------------------------------------------------------


def _comment_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--text", required=True)


@app.verb("comment", add_args=_comment_args, requires_commit_flag=True)
def comment(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Comment on the current note detail.

    Default = dry-run (open compose, type text, locate send button, cancel).
    With --commit (and EM_ALLOW_COMMIT=1 gated by cli), actually press send.
    """
    ctx.linter.check_or_raise(args.text)
    ctx.governor.check_or_raise("comment")

    # IME handling: type_text_humanized's CJK path swaps to ADBKeyboard then
    # restores the original IME — that restore drops focus and dismisses the
    # compose overlay before we can locate the send button. So for CJK text we
    # pre-swap ADBKeyboard BEFORE opening compose (a soft-input window change
    # while compose is open also dismisses it) and only restore at the very end.
    needs_cjk = not args.text.isascii()
    prev_ime = _ime.current_ime(ctx.device) if needs_cjk else None
    if needs_cjk:
        _ime.set_adbkeyboard(ctx.device)
        time.sleep(0.6)

    try:
        xml = Path(ctx.ui.dump()["path"]).read_text()
        compose = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/mContentET")
        if compose is None:
            # New XHS detail page: tap the bottom "说点什么..." bar (inputCommentTV)
            # to open compose. Older builds used noteCommentLayout.
            cta = None
            for rid in (
                "com.xingin.xhs:id/inputCommentTV",
                "com.xingin.xhs:id/noteCommentLayout",
            ):
                cta = ctx.ui.find_by_resource_id(xml, rid)
                if cta is not None:
                    break
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
        if needs_cjk:
            ctx.device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(args.text)}")
        else:
            ctx.input.type_text(args.text)
        time.sleep(1.5)

        xml = Path(ctx.ui.dump()["path"]).read_text()
        send_btn = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/commentFuncBtnSend")
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
    finally:
        if needs_cjk and prev_ime:
            _ime.restore_ime(ctx.device, prev_ime)


# ----- reply (二级追评) ---------------------------------------------------------


def _scroll_to_comments(ctx: ExecContext, max_swipes: int = 5) -> list[CommentRow]:
    """Swipe up on the note detail until top-level comments come into view.

    Mirrors spec §3.4 step1: the verb ensures comments are visible (already
    there -> no-op). Returns the parsed rows from the final screen state.
    """
    rows = _parse_comment_rows(Path(ctx.ui.dump()["path"]).read_text())
    swipes = 0
    while not rows and swipes < max_swipes:
        ctx.input.swipe((540, 1800), (540, 700))
        time.sleep(1.0)
        rows = _parse_comment_rows(Path(ctx.ui.dump()["path"]).read_text())
        swipes += 1
    return rows


def _reply_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rank", type=int, help="reply to the Nth visible comment")
    p.add_argument("--match", help="reply to first visible comment containing this text")
    p.add_argument("--text", required=True)


@app.verb("reply", add_args=_reply_args, requires_commit_flag=True)
def reply(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Reply to a comment on the current note (creates a 2nd-level reply).

    Select target by --rank N or --match "kw" (exactly one). Default = dry-run
    (locate target + send button, cancel). --commit actually sends.
    Scrolls the note detail to bring comments into view if needed.
    """
    ctx.linter.check_or_raise(args.text)
    ctx.governor.check_or_raise("comment")

    rows = _scroll_to_comments(ctx)
    if not rows:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "no comments found after scrolling",
            hint="open a note detail first via `xiaohongshu open --rank N`",
        )
    target = select_comment(rows, rank=args.rank, match=args.match)

    # CJK: pre-swap ADBKeyboard before opening compose; restore at the very end
    # (an IME change while compose is open dismisses it -- same as `comment`).
    needs_cjk = not args.text.isascii()
    prev_ime = _ime.current_ime(ctx.device) if needs_cjk else None
    if needs_cjk:
        _ime.set_adbkeyboard(ctx.device)
        time.sleep(0.6)

    try:
        # Tap the 回复 affordance: it's the right-end word of the time/region line
        # ("04-17 河北 回复"). Center is the date, so tap near the right edge.
        rn = target.reply_node
        ctx.input.tap_xy(rn["bounds"][2] - 40, rn["cy"])
        time.sleep(1.5)

        xml = Path(ctx.ui.dump()["path"]).read_text()
        compose = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/mContentET")
        if compose is None and target.content_node is not None:
            # Fallback: right-edge tap missed the 回复 span -> tap the comment
            # text itself (also opens the reply compose on this build).
            ctx.input.tap_node(target.content_node)
            time.sleep(1.5)
            xml = Path(ctx.ui.dump()["path"]).read_text()
            compose = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/mContentET")
        if compose is None:
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                "XHS reply compose not visible",
                hint="tapping 回复 did not open the compose box; verify tap point with screenshot",
            )

        ctx.input.tap_node(compose)
        time.sleep(1.0)
        if needs_cjk:
            ctx.device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(args.text)}")
        else:
            ctx.input.type_text(args.text)
        time.sleep(1.5)

        xml = Path(ctx.ui.dump()["path"]).read_text()
        send_btn = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/commentFuncBtnSend")
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


# ----- engage (search → iterate → like / comment) ------------------------------


def _on_results_page(ctx: ExecContext) -> bool:
    xml = Path(ctx.ui.dump()["path"]).read_text()
    return bool(_find_result_cards(ctx, xml))


def _back_to_results(ctx: ExecContext, max_back: int = 6) -> bool:
    for _ in range(max_back):
        if _on_results_page(ctx):
            return True
        ctx.input.keyevent("back")
        time.sleep(1.2)
    return _on_results_page(ctx)


def _engage_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--keyword", required=True)
    p.add_argument("--limit", type=int, default=3, help="how many top results to engage with")
    p.add_argument("--like", action="store_true", help="like each note")
    p.add_argument("--comment-text", dest="comment_text", help="post this comment on each note")
    p.add_argument("--sleep", type=float, default=2.0, help="seconds between iterations")


@app.verb("engage", add_args=_engage_args, requires_commit_flag=True)
def engage(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """Search a keyword, then iterate top results doing like / comment.

    Pipeline per iteration: open → detail → (like) → (comment) → back-to-results.
    Each mutating step honors --commit (passed through to the underlying verbs).
    At least one of --like / --comment-text must be provided.
    """
    if not args.like and not args.comment_text:
        raise EmError(
            ErrorCode.UNKNOWN,
            "engage requires at least one of --like or --comment-text",
        )

    if args.comment_text:
        ctx.linter.check_or_raise(args.comment_text)

    search_result = search(
        argparse.Namespace(keyword=args.keyword, limit=args.limit),
        ctx,
    )
    hits = search_result["results"]

    iterations: list[dict[str, Any]] = []
    for hit in hits:
        # Before each iteration: ensure we're on the results page. If a prior
        # iteration left us stranded (compose overlay, sub-page), re-run search
        # from home to get a clean state.
        if not _on_results_page(ctx):
            search(
                argparse.Namespace(keyword=args.keyword, limit=args.limit),
                ctx,
            )

        rank = hit["index"]
        item: dict[str, Any] = {"rank": rank}
        try:
            open_result(argparse.Namespace(rank=rank), ctx)
            item["detail"] = detail(argparse.Namespace(), ctx)

            if args.like:
                item["like"] = like(
                    argparse.Namespace(commit=getattr(args, "commit", False)),
                    ctx,
                )

            if args.comment_text:
                item["comment"] = comment(
                    argparse.Namespace(
                        text=args.comment_text,
                        commit=getattr(args, "commit", False),
                    ),
                    ctx,
                )
        except EmError as e:
            item["error"] = {"code": e.code.name, "message": str(e)}

        item["recovered_to_results"] = _back_to_results(ctx)
        iterations.append(item)
        time.sleep(args.sleep)

    return {
        "keyword": args.keyword,
        "limit": args.limit,
        "did_like": args.like,
        "did_comment": bool(args.comment_text),
        "iterations": iterations,
    }


_ME_TAB_XY = (972, 2288)  # bottom nav 我 (index_me center @1080x2410)


def _dismiss_unfinished_draft(ctx: ExecContext) -> None:
    """若弹「继续编辑笔记吗?」草稿恢复弹窗,点关闭(不存草稿、不去编辑)。"""
    xml = Path(ctx.ui.dump()["path"]).read_text()
    btn = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/btn_unfinished_draft_dialog_exit")
    if btn is not None:
        ctx.input.tap_node(btn)
        time.sleep(0.8)


def _profile_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--avatar-out", default=None, help="头像 PNG 落盘路径")


@app.verb("profile", add_args=_profile_args)
def profile(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """读取登录态;已登录则返回头像(裁剪PNG)/昵称/小红书号/计数/简介。"""
    # 必须先可靠回首页(底部导航在位)再点「我」tab;否则非首页态下硬点坐标会落空 →
    # dump 到错屏 → 误报未登录。(ensure_foreground 不导航,是之前假阴性的根因。)
    _ensure_home(ctx)
    _dismiss_unfinished_draft(ctx)
    ctx.input.tap_xy(*_ME_TAB_XY)  # 我 tab
    time.sleep(2.0)
    _dismiss_unfinished_draft(ctx)

    xml = Path(ctx.ui.dump()["path"]).read_text()
    info = _parse_profile(xml)
    if not info.get("logged_in"):
        return {"logged_in": False}

    bounds = info.pop("avatar_bounds", None)
    if bounds is not None:
        shot = ctx.ui.screenshot_region(bounds, args.avatar_out)
        info["avatar"] = shot["path"]
    else:
        info["avatar"] = None
    return info


# ----- publish (arg pure-fns) ---------------------------------------------------

# ===== publish (00-selectors-publish.md) =====
# 纯逻辑(classify_media / parse_tags / order_media_for_cover)已抽到
# mobilecli.apps._publish,三家 app 共用;此处以别名导入保留内部调用名。
# 点击坐标(tuple)单列,与 resource-id(str)分开,类型清晰。
_PUB_XY: dict[str, tuple[int, int]] = {
    "post_entry": (540, 2288),  # id/index_post
    "album_from_gallery": (540, 1775),  # 面板 id/rlFirst 从相册选择
}

_PUB = {
    "go_next": "com.xingin.xhs:id/bottomGoNext",  # 选完下一步
    "edit_next": "com.xingin.xhs:id/capa_light_edit_next",
    "title": "com.xingin.xhs:id/editTitle",
    "body": "com.xingin.xhs:id/postNoteEditContentView",
    "add_topic": "com.xingin.xhs:id/addTopicView",
    "topic_name": "com.xingin.xhs:id/tvTopicName",
    "cover_entry": "com.xingin.xhs:id/bottomEditCoverAreaV2",
    "cover_album_btn": "com.xingin.xhs:id/album_cover_layout",
    "cover_thumb": "com.xingin.xhs:id/thumbnailIv",
    "cover_done": "com.xingin.xhs:id/btnDone",
    "cover_edit_done": "com.xingin.xhs:id/rightTv",
    "publish_btn": "com.xingin.xhs:id/capaBigPostBtn",
    "loc_refuse": "com.xingin.xhs:id/text_refuse",
    "select_circle": "com.xingin.xhs:id/selectableLayout",
    "no_perm_text": "去开启权限",
}

_DECLARE_TEXT = {
    "ai": "含 AI 合成内容",
    "original": "内容为自行拍摄",
    "repost": "内容为转载",
    "fiction": "含虚构演绎内容",
    "marketing": "内容含营销信息",
    "opinion": "个人观点，仅供参考",
}


def _select_pushed_media(ctx: ExecContext, count: int) -> None:
    """点前 count 个网格单元的选择圈(推入素材已 touch 到相册最前)。"""
    xml = Path(ctx.ui.dump()["path"]).read_text()
    circles = ctx.ui.find_all_by_resource_id(xml, _PUB["select_circle"])
    if len(circles) < count:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            f"album shows {len(circles)} selectable items, need {count}",
            hint="pushed media not visible; check READ_MEDIA permission / scan",
        )
    for i in range(count):
        ctx.input.tap_node(circles[i])
        time.sleep(0.6)
    go = ctx.ui.find_by_resource_id(Path(ctx.ui.dump()["path"]).read_text(), _PUB["go_next"])
    if go is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "下一步 button not found")
    ctx.input.tap_node(go)
    time.sleep(3)


def _type_cjk(ctx: ExecContext, node: dict[str, Any], text: str) -> None:
    """点输入框 + ADBKeyboard 输入 + 回查重试(CJK 时切 ADBKeyboard 末尾恢复)。"""
    needs_cjk = not text.isascii()
    prev = _ime.current_ime(ctx.device) if needs_cjk else None
    if needs_cjk:
        _ime.set_adbkeyboard(ctx.device)
        time.sleep(0.6)
    try:
        ctx.input.tap_node(node)
        time.sleep(1.0)
        for _attempt in range(2):
            if needs_cjk:
                ctx.device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(text)}")
            else:
                ctx.input.type_text(text)
            time.sleep(1.2)
            xml = Path(ctx.ui.dump()["path"]).read_text()
            if text[:6] in xml:
                return
    finally:
        if needs_cjk and prev:
            _ime.restore_ime(ctx.device, prev)


def _add_topics(ctx: ExecContext, tags: list[str]) -> list[bool]:
    linked: list[bool] = []
    for t in tags:
        xml = Path(ctx.ui.dump()["path"]).read_text()
        btn = ctx.ui.find_by_resource_id(xml, _PUB["add_topic"])
        if btn is None:
            linked.append(False)
            continue
        ctx.input.tap_node(btn)
        time.sleep(1.0)
        _ime.set_adbkeyboard(ctx.device)
        time.sleep(0.4)
        ctx.device.shell(f"am broadcast -a ADB_INPUT_TEXT --es msg {shlex.quote(t)}")
        time.sleep(1.5)
        xml = Path(ctx.ui.dump()["path"]).read_text()
        rows = ctx.ui.find_all_by_resource_id(xml, _PUB["topic_name"])
        if rows:
            ctx.input.tap_node(rows[0])
            time.sleep(1.0)
            linked.append(True)
        else:
            linked.append(False)
    return linked


def _set_declare(ctx: ExecContext, declare: str) -> None:
    if declare == "none":
        return
    xml = Path(ctx.ui.dump()["path"]).read_text()
    entry = ctx.ui.find_by_resource_id(xml, "com.xingin.xhs:id/declareTv")
    if entry is None:
        return
    ctx.input.tap_node(entry)
    time.sleep(2.0)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    opt = ctx.ui.find_by_text(xml, _DECLARE_TEXT[declare])
    if opt is not None:
        ctx.input.tap_node(opt)
        time.sleep(0.8)
    ctx.input.keyevent("back")
    time.sleep(1.0)


def _set_video_cover(ctx: ExecContext) -> None:
    """视频自定义封面:选封面->+相册->选图(已 touch 到最前)->下一步->制作封面完成。"""
    xml = Path(ctx.ui.dump()["path"]).read_text()
    entry = ctx.ui.find_by_resource_id(xml, _PUB["cover_entry"])
    if entry is None:
        return
    ctx.input.tap_node(entry)
    time.sleep(2.5)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    alb = ctx.ui.find_by_resource_id(xml, _PUB["cover_album_btn"])
    if alb is None:
        ctx.input.keyevent("back")
        return
    ctx.input.tap_node(alb)
    time.sleep(3)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    thumbs = ctx.ui.find_all_by_resource_id(xml, _PUB["cover_thumb"])
    if thumbs:
        ctx.input.tap_node(thumbs[0])
        time.sleep(3)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    done = ctx.ui.find_by_resource_id(xml, _PUB["cover_done"])
    if done:
        ctx.input.tap_node(done)
        time.sleep(3)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    edit_done = ctx.ui.find_by_resource_id(xml, _PUB["cover_edit_done"])
    if edit_done:
        ctx.input.tap_node(edit_done)
        time.sleep(2.5)


def _publish_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--media", nargs="+", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--tags", default=None)
    p.add_argument("--cover", default=None, help="图文: 第N张(int); 视频: 封面图路径")
    p.add_argument(
        "--declare",
        default="none",
        choices=["none", "ai", "original", "repost", "fiction", "marketing", "opinion"],
    )


@app.verb("publish", add_args=_publish_args, requires_commit_flag=True)
def publish(args: argparse.Namespace, ctx: ExecContext) -> dict[str, Any]:
    """发布图文/视频。默认 dry-run(走到发布键前停);--commit 真发。"""
    # 1. lint + 判型 + cover 参数合法性
    ctx.linter.check_or_raise(args.title)
    ctx.linter.check_or_raise(args.body)
    tags = _parse_tags(args.tags)
    for t in tags:
        ctx.linter.check_or_raise(t)
    media_type = _classify_media(args.media)

    cover_index = None
    cover_path = None
    if args.cover is not None:
        if media_type == "image":
            if not args.cover.isdigit():
                raise EmError(ErrorCode.INVALID_ARG, "图文 --cover 需为第N张(整数)")
            cover_index = int(args.cover)
        else:
            cover_path = args.cover
            _classify_media([cover_path])  # 复用扩展名校验(单文件)

    # 2. 推素材(图文按封面顺序;视频单个;cover_path 一并推)
    media = args.media
    if media_type == "image":
        media = _order_media_for_cover(media, cover_index)
    # cover_path 最后推 -> mtime 最新 -> 相册「最近」排第一格 -> _set_video_cover 取 thumbs[0]。
    # 若改动推送顺序,务必同步 _set_video_cover 的索引。
    to_push = list(media) + ([cover_path] if cover_path else [])
    pushed = ctx.media.push_to_gallery(to_push)

    commit = getattr(args, "commit", False)
    if commit:
        ctx.governor.check_or_raise("publish")

    steps: list[str] = [f"pushed {pushed['count']} media ({media_type})"]

    # 3. 进相册
    _ensure_home(ctx)
    _dismiss_unfinished_draft(ctx)
    ctx.input.tap_xy(*_PUB_XY["post_entry"])
    time.sleep(2)
    ctx.input.tap_xy(*_PUB_XY["album_from_gallery"])
    time.sleep(3)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    if _PUB["no_perm_text"] in xml:
        raise EmError(
            ErrorCode.PERMISSION_REQUIRED,
            "小红书无完整相册权限,无法读取推入素材",
            hint="adb shell pm grant com.xingin.xhs android.permission.READ_MEDIA_IMAGES "
            "&& ...READ_MEDIA_VIDEO",
        )
    steps.append("opened album")

    # 4. 选素材(前 len(media) 格)
    _select_pushed_media(ctx, count=len(media))
    steps.append(f"selected {len(media)} item(s)")

    # 5. 编辑页(图文/视频选完都进一道编辑页 ImageEditActivity3/VideoEditActivityV3)
    #    -> 下一步到发布编辑页。两者「下一步」同 id capa_light_edit_next。
    xml = Path(ctx.ui.dump()["path"]).read_text()
    edit_next = ctx.ui.find_by_resource_id(xml, _PUB["edit_next"])
    if edit_next is not None:
        ctx.input.tap_node(edit_next)
        time.sleep(3)
        steps.append("passed edit page")
    elif media_type == "video":
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "video edit 下一步 not found")

    # 6. 编辑页:取消位置弹窗
    xml = Path(ctx.ui.dump()["path"]).read_text()
    refuse = ctx.ui.find_by_resource_id(xml, _PUB["loc_refuse"])
    if refuse is not None:
        ctx.input.tap_node(refuse)
        time.sleep(1.5)

    # 7. 标题 + 正文
    xml = Path(ctx.ui.dump()["path"]).read_text()
    title_node = ctx.ui.find_by_resource_id(xml, _PUB["title"])
    body_node = ctx.ui.find_by_resource_id(xml, _PUB["body"])
    if title_node is None or body_node is None:
        raise EmError(
            ErrorCode.ELEMENT_NOT_FOUND,
            "compose title/body not found",
            hint="check 00-selectors-publish.md CapaPostNotePlatformActivity",
        )
    _type_cjk(ctx, title_node, args.title)
    # 输完标题后重新定位正文框(坐标可能漂移);找不到则回退到上面已校验的节点。
    body_node = (
        ctx.ui.find_by_resource_id(Path(ctx.ui.dump()["path"]).read_text(), _PUB["body"])
        or body_node
    )
    _type_cjk(ctx, body_node, args.body)
    steps.append("filled title+body")

    # 8. 话题
    tags_linked = _add_topics(ctx, tags) if tags else []
    if tags:
        steps.append(f"topics linked={tags_linked}")

    # 9. 视频自定义封面
    if media_type == "video" and cover_path:
        _set_video_cover(ctx)
        steps.append("set custom cover")

    # 10. 声明
    if args.declare != "none":
        _set_declare(ctx, args.declare)
        steps.append(f"declare={args.declare}")

    # 11. 收键盘 + 定位发布键
    ctx.input.keyevent("back")
    time.sleep(1.0)
    xml = Path(ctx.ui.dump()["path"]).read_text()
    pub_btn = ctx.ui.find_by_resource_id(xml, _PUB["publish_btn"])
    if pub_btn is None:
        raise EmError(ErrorCode.ELEMENT_NOT_FOUND, "发布笔记 button not found")
    steps.append("reached 发布笔记")
    shot = ctx.ui.screenshot()["path"]

    base = {
        "media_type": media_type,
        "pushed": pushed["pushed"],
        "title": args.title,
        "body_len": len(args.body),
        "tags": tags,
        "tags_linked": tags_linked,
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
    xml = Path(ctx.ui.dump()["path"]).read_text()
    verified = (
        str(ctx.app.foreground().get("activity", "")).endswith(_HOME_ACTIVITY_SUFFIX)
        or "发布成功" in xml
    )
    ctx.governor.record("publish")
    return {"dry_run": False, "committed": True, "verified_published": verified, **base}
