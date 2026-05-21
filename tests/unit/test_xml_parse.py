"""Offline tests for UI XML parsing -- uses fixture XMLs."""

from __future__ import annotations

from pathlib import Path

from mobilecli.core.ui import (
    find_by_content_desc,
    find_by_resource_id,
    parse_bounds,
)

FIX = Path(__file__).parent.parent / "fixtures"


def test_parse_bounds_normal():
    assert parse_bounds("[10,20][100,200]") == (10, 20, 100, 200)


def test_parse_bounds_returns_none_on_garbage():
    assert parse_bounds("not bounds") is None


def test_find_by_resource_id_xhs_search_input():
    xml = (FIX / "xhs-search-page.xml").read_text()
    node = find_by_resource_id(xml, "com.xingin.xhs:id/mSearchToolBarEt")
    assert node is not None
    assert node["cx"] > 0 and node["cy"] > 0


def test_find_by_content_desc_douyin_search():
    xml = (FIX / "douyin-home.xml").read_text()
    node = find_by_content_desc(xml, "搜索")
    assert node is not None
    assert node["bounds"] is not None
