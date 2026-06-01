"""_parse_douyin_profile: 抖音我页 xml -> 登录态/昵称/抖音号/计数/头像bounds。"""
from __future__ import annotations

from pathlib import Path

from mobilecli.apps.douyin import _parse_douyin_profile

FIX = Path(__file__).parent.parent / "fixtures"


def test_parse_logged_in():
    p = _parse_douyin_profile((FIX / "douyin-profile.xml").read_text())
    assert p["logged_in"] is True
    assert p["nickname"] == "测试昵称"
    assert p["douyin_id"] == "test_dyid"
    assert p["likes_count"] == 3046
    assert p["following_count"] == 14
    assert p["fans_count"] == 227
    assert p["avatar_bounds"] is not None
    assert len(p["avatar_bounds"]) == 4


def test_parse_logged_out():
    xml = '<hierarchy><node resource-id="x" bounds="[0,0][1,1]"/></hierarchy>'
    p = _parse_douyin_profile(xml)
    assert p["logged_in"] is False
