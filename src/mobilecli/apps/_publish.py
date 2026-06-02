"""Shared publish helpers -- media classification, tag + cover parsing.

Pure logic over CLI args; no device access (testable without a phone). The
platform-specific publish UI walk (selectors, edit-page steps, declare option
labels) lives in each app (xiaohongshu / douyin / kuaishou).
"""

from __future__ import annotations

from pathlib import Path

from mobilecli.envelope import EmError, ErrorCode

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXT = {".mp4", ".mov"}


def classify_media(paths: list[str]) -> str:
    """全图片->'image';恰好 1 视频且无图->'video';否则 INVALID_ARG。"""
    exts = [Path(p).suffix.lower() for p in paths]
    imgs = [e for e in exts if e in IMAGE_EXT]
    vids = [e for e in exts if e in VIDEO_EXT]
    bad = [e for e in exts if e not in IMAGE_EXT | VIDEO_EXT]
    if bad:
        raise EmError(ErrorCode.INVALID_ARG, f"unsupported media: {bad}")
    if imgs and not vids:
        return "image"
    if len(vids) == 1 and not imgs:
        return "video"
    raise EmError(
        ErrorCode.INVALID_ARG,
        "media must be all images OR exactly one video (no mix)",
    )


def parse_tags(s: str | None) -> list[str]:
    """逗号分隔 -> 去空白 -> 丢空项。"""
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


def order_media_for_cover(media: list[str], cover_index: int | None) -> list[str]:
    """图文:把第 cover_index 张(1-based)排到首位;越界/None 原序返回。"""
    if cover_index is None or cover_index < 1 or cover_index > len(media):
        return list(media)
    i = cover_index - 1
    return [media[i]] + media[:i] + media[i + 1 :]


def resolve_cover(media_type: str, cover_arg: str | None) -> tuple[int | None, str | None]:
    """解析 --cover:图文需第 N 张(整数)-> (index, None);视频需图片路径 -> (None, path)。

    返回 (cover_index, cover_path),二者至多一个非空。非法输入抛 INVALID_ARG。
    """
    if cover_arg is None:
        return (None, None)
    if media_type == "image":
        # 1-based;拒绝 0 / 非数字(否则会静默退化成 default,误导调用方)。
        if not cover_arg.isdigit() or int(cover_arg) < 1:
            raise EmError(ErrorCode.INVALID_ARG, "图文 --cover 需为第N张(正整数,从1起)")
        return (int(cover_arg), None)
    classify_media([cover_arg])  # 复用扩展名校验(单文件)
    return (None, cover_arg)
