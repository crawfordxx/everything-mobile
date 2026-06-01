from __future__ import annotations

import pytest

from mobilecli.apps.xiaohongshu import (
    _classify_media,
    _order_media_for_cover,
    _parse_tags,
    _to_int,
)
from mobilecli.envelope import EmError, ErrorCode


def test_classify_images():
    assert _classify_media(["a.jpg", "b.PNG"]) == "image"


def test_classify_single_video():
    assert _classify_media(["v.mp4"]) == "video"


def test_classify_mixed_rejected():
    with pytest.raises(EmError) as e:
        _classify_media(["a.jpg", "v.mp4"])
    assert e.value.code == ErrorCode.INVALID_ARG


def test_classify_multi_video_rejected():
    with pytest.raises(EmError) as e:
        _classify_media(["a.mp4", "b.mp4"])
    assert e.value.code == ErrorCode.INVALID_ARG


def test_parse_tags():
    assert _parse_tags("AI视频, 教程 ,") == ["AI视频", "教程"]
    assert _parse_tags(None) == []


def test_order_media_for_cover_index():
    assert _order_media_for_cover(["a", "b", "c"], cover_index=2) == ["b", "a", "c"]


def test_order_media_for_cover_default():
    assert _order_media_for_cover(["a", "b"], cover_index=None) == ["a", "b"]


def test_order_media_for_cover_out_of_range():
    # cover_index 越界(>len 或 <1)-> 原序返回,不抛
    assert _order_media_for_cover(["a", "b"], cover_index=9) == ["a", "b"]
    assert _order_media_for_cover(["a", "b"], cover_index=0) == ["a", "b"]


def test_to_int_units_and_edge_cases():
    assert _to_int("15") == 15
    assert _to_int("1.2万") == 12000
    assert _to_int("3亿") == 300_000_000
    assert _to_int("") == 0
    assert _to_int("粉丝数，1个") == 1  # 内嵌数字 content-desc
