"""Offline tests for Xiaohongshu comment-row parsing -- uses fixture XML."""

from __future__ import annotations

from pathlib import Path

from mobilecli.apps.xiaohongshu import _parse_comment_rows

FIX = Path(__file__).parent.parent / "fixtures"


def _xml() -> str:
    return (FIX / "xhs-comments.xml").read_text()


def test_parses_only_toplevel_rows():
    rows = _parse_comment_rows(_xml())
    # 3 条顶层评论(子楼 subCommentLayout 内的回复被 x<180 过滤掉)
    assert len(rows) == 3
    assert [r.index for r in rows] == [1, 2, 3]


def test_row_text_is_tv_content():
    rows = _parse_comment_rows(_xml())
    assert rows[0].text.strip() == "测试评论一"
    assert rows[1].text.strip() == "测试评论二"
    assert rows[2].text.strip() == "测试评论三"


def test_reply_node_is_toplevel_time_reply_line():
    rows = _parse_comment_rows(_xml())
    n = rows[0].reply_node
    assert "回复" in n["text"]
    assert n["bounds"][0] < 180  # top-level, not indented sub-reply
    assert n["bounds"][1] >= 797  # reply line sits below its comment text


def test_content_node_stored_for_fallback():
    rows = _parse_comment_rows(_xml())
    assert rows[0].content_node is not None
    assert rows[0].content_node["text"].strip() == "测试评论一"
