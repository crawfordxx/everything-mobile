"""Offline tests for comment-row selection (rank / match)."""

from __future__ import annotations

import pytest

from mobilecli.apps._comments import CommentRow, select_comment
from mobilecli.envelope import EmError, ErrorCode


def _rows() -> list[CommentRow]:
    return [
        CommentRow(index=1, text="用户A,第一条评论", reply_node={"cx": 10, "cy": 10}),
        CommentRow(index=2, text="用户B,多少钱啊", reply_node={"cx": 20, "cy": 20}),
        CommentRow(index=3, text="用户C,第三条", reply_node={"cx": 30, "cy": 30}),
    ]


def test_select_by_rank_returns_nth():
    row = select_comment(_rows(), rank=2, match=None)
    assert row.index == 2
    assert row.reply_node["cy"] == 20


def test_select_by_match_returns_first_containing():
    row = select_comment(_rows(), rank=None, match="多少钱")
    assert row.index == 2


def test_rank_out_of_range_raises_element_not_found():
    with pytest.raises(EmError) as ei:
        select_comment(_rows(), rank=9, match=None)
    assert ei.value.code == ErrorCode.ELEMENT_NOT_FOUND


def test_match_no_hit_raises_element_not_found():
    with pytest.raises(EmError) as ei:
        select_comment(_rows(), rank=None, match="不存在")
    assert ei.value.code == ErrorCode.ELEMENT_NOT_FOUND


def test_neither_rank_nor_match_raises_unknown():
    with pytest.raises(EmError) as ei:
        select_comment(_rows(), rank=None, match=None)
    assert ei.value.code == ErrorCode.UNKNOWN


def test_both_rank_and_match_raises_unknown():
    with pytest.raises(EmError) as ei:
        select_comment(_rows(), rank=1, match="第一条")
    assert ei.value.code == ErrorCode.UNKNOWN
