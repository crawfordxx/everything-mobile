"""Tests for the shared publish helpers (apps/_publish.py).

Pure logic only -- no device access. These are the platform-agnostic pieces
shared by xiaohongshu / douyin / kuaishou publish verbs.
"""

from __future__ import annotations

import pytest

from mobilecli.apps._publish import (
    classify_media,
    order_media_for_cover,
    parse_tags,
    resolve_cover,
)
from mobilecli.envelope import EmError, ErrorCode

# ----- classify_media ----------------------------------------------------------


def test_classify_images():
    assert classify_media(["a.jpg", "b.PNG", "c.webp"]) == "image"


def test_classify_single_video():
    assert classify_media(["v.mp4"]) == "video"
    assert classify_media(["v.MOV"]) == "video"


def test_classify_mixed_rejected():
    with pytest.raises(EmError) as e:
        classify_media(["a.jpg", "v.mp4"])
    assert e.value.code == ErrorCode.INVALID_ARG


def test_classify_multi_video_rejected():
    with pytest.raises(EmError) as e:
        classify_media(["a.mp4", "b.mp4"])
    assert e.value.code == ErrorCode.INVALID_ARG


def test_classify_unsupported_ext_rejected():
    with pytest.raises(EmError) as e:
        classify_media(["a.gif"])
    assert e.value.code == ErrorCode.INVALID_ARG


# ----- parse_tags --------------------------------------------------------------


def test_parse_tags_basic():
    assert parse_tags("AI视频, 教程 ,") == ["AI视频", "教程"]


def test_parse_tags_none_and_empty():
    assert parse_tags(None) == []
    assert parse_tags("") == []
    assert parse_tags("  ,  ,") == []


# ----- order_media_for_cover ---------------------------------------------------


def test_order_media_for_cover_index():
    assert order_media_for_cover(["a", "b", "c"], cover_index=2) == ["b", "a", "c"]


def test_order_media_for_cover_default():
    assert order_media_for_cover(["a", "b"], cover_index=None) == ["a", "b"]


def test_order_media_for_cover_out_of_range():
    assert order_media_for_cover(["a", "b"], cover_index=9) == ["a", "b"]
    assert order_media_for_cover(["a", "b"], cover_index=0) == ["a", "b"]


# ----- resolve_cover -----------------------------------------------------------


def test_resolve_cover_none():
    assert resolve_cover("image", None) == (None, None)
    assert resolve_cover("video", None) == (None, None)


def test_resolve_cover_image_index():
    assert resolve_cover("image", "2") == (2, None)


def test_resolve_cover_image_non_digit_rejected():
    with pytest.raises(EmError) as e:
        resolve_cover("image", "abc")
    assert e.value.code == ErrorCode.INVALID_ARG


def test_resolve_cover_image_zero_rejected():
    # cover 是 1-based;'0' 虽 isdigit 但无意义,必须拒绝(否则静默退化成 default)。
    with pytest.raises(EmError) as e:
        resolve_cover("image", "0")
    assert e.value.code == ErrorCode.INVALID_ARG


def test_resolve_cover_video_path():
    assert resolve_cover("video", "/tmp/cover.jpg") == (None, "/tmp/cover.jpg")


def test_resolve_cover_video_bad_ext_rejected():
    with pytest.raises(EmError) as e:
        resolve_cover("video", "/tmp/cover.txt")
    assert e.value.code == ErrorCode.INVALID_ARG
