"""Offline tests for Kuaishou comment-row parsing -- uses fixture XML."""

from __future__ import annotations

from pathlib import Path

from mobilecli.apps.kuaishou import _parse_comment_rows

FIX = Path(__file__).parent.parent / "fixtures"


def _xml() -> str:
    return (FIX / "kuaishou-comments.xml").read_text()


def test_parses_visible_rows():
    rows = _parse_comment_rows(_xml())
    assert len(rows) == 6
    assert [r.index for r in rows] == [1, 2, 3, 4, 5, 6]


def test_row_text_is_comment_node():
    rows = _parse_comment_rows(_xml())
    assert "扒拉出来" in rows[0].text
    assert rows[1].text == "有洁癖的猫猫"
    assert "太聪明了" in rows[2].text


def test_reply_node_is_comment_reply():
    rows = _parse_comment_rows(_xml())
    n = rows[0].reply_node
    assert "回复" in (n["text"] + n["content_desc"])


def test_content_node_paired_in_same_frame():
    rows = _parse_comment_rows(_xml())
    # reply button sits below its comment text within the same comment_frame
    for r in rows:
        assert r.content_node is not None
        assert r.reply_node["bounds"][1] >= r.content_node["bounds"][1]
