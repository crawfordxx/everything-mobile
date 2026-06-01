"""_parse_profile: 从我页 xml 抽登录态/昵称/计数/简介/头像bounds。"""
from __future__ import annotations

from pathlib import Path

from mobilecli.apps.xiaohongshu import _parse_profile

FIX = Path(__file__).parent.parent / "fixtures"


def test_parse_logged_in():
    p = _parse_profile((FIX / "xhs-profile.xml").read_text())
    assert p["logged_in"] is True
    assert p["nickname"] == "测试昵称"
    assert p["red_id"] == "test_red_id"
    assert p["ip"] == "北京"
    assert p["follow_count"] == 2
    assert p["fans_count"] == 29
    assert p["fav_count"] == 197
    assert "测试简介" in p["bio"]
    assert p["avatar_bounds"] is not None
    assert len(p["avatar_bounds"]) == 4


def test_parse_logged_out():
    xml = '<hierarchy><node resource-id="x" bounds="[0,0][1,1]"/></hierarchy>'
    p = _parse_profile(xml)
    assert p["logged_in"] is False
