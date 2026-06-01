"""Offline tests for Douyin comment-row parsing -- uses fixture XML."""

from __future__ import annotations

from pathlib import Path

from mobilecli.apps.douyin import _parse_comment_rows

FIX = Path(__file__).parent.parent / "fixtures"


def _xml() -> str:
    return (FIX / "douyin-comments.xml").read_text()


def test_parses_visible_toplevel_rows():
    rows = _parse_comment_rows(_xml())
    # 3 个可见回复键(末行 fco 的 xdh 被 RecyclerView 底边裁掉)
    assert len(rows) == 3
    assert [r.index for r in rows] == [1, 2, 3]


def test_row_text_comes_from_fco_content_desc():
    rows = _parse_comment_rows(_xml())
    assert "我看上他了" in rows[0].text
    assert "女主好美" in rows[1].text
    assert "跪求一双" in rows[2].text


def test_reply_node_center_inside_its_fco():
    rows = _parse_comment_rows(_xml())
    # 第一行回复键中心落在第一个 fco [0,1055][1080,1330] 区间
    n = rows[0].reply_node
    assert 0 <= n["cx"] <= 1080
    assert 1055 <= n["cy"] <= 1330
    assert "回复" in n["text"]
