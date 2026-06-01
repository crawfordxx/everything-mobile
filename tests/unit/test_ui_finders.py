"""Offline tests for content-desc / class UI finders -- uses fixture XML."""

from __future__ import annotations

from pathlib import Path

from mobilecli.core.ui import find_by_content_desc_contains, find_first_by_class

FIX = Path(__file__).parent.parent / "fixtures"


def _dy() -> str:
    return (FIX / "douyin-comments.xml").read_text()


def test_content_desc_contains_hit():
    # fco content-desc ends with "...回复 按钮,"
    node = find_by_content_desc_contains(_dy(), "回复", "按钮")
    assert node is not None
    assert "回复" in node["content_desc"] and "按钮" in node["content_desc"]


def test_content_desc_contains_all_needles_required():
    assert find_by_content_desc_contains(_dy(), "回复", "这串绝不存在xyz") is None


def test_content_desc_contains_miss():
    assert find_by_content_desc_contains(_dy(), "这串绝不存在xyz") is None


def test_first_by_class_finds_edittext():
    # the comments overlay has an inline compose EditText (eoy)
    node = find_first_by_class(_dy(), "EditText")
    assert node is not None
    assert "EditText" in node["class"]


def test_first_by_class_miss():
    assert find_first_by_class(_dy(), "android.widget.DatePicker") is None
