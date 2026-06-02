"""_parse_kuaishou_profile: 快手我页 xml -> 登录态/昵称/快手号/计数/头像bounds。"""

from __future__ import annotations

from pathlib import Path

from mobilecli.apps.kuaishou import _parse_kuaishou_profile

FIX = Path(__file__).parent.parent / "fixtures"


def test_parse_logged_in():
    p = _parse_kuaishou_profile((FIX / "kuaishou-profile.xml").read_text())
    assert p["logged_in"] is True
    assert p["nickname"] == "测试用户KS"
    assert p["kwai_id"] == "1234567890"
    assert p["fans_count"] == 1
    assert p["following_count"] == 1
    assert p["likes_count"] == 15
    assert p["avatar_bounds"] is not None
    assert len(p["avatar_bounds"]) == 4


def test_parse_logged_out():
    xml = '<hierarchy><node resource-id="x" bounds="[0,0][1,1]"/></hierarchy>'
    p = _parse_kuaishou_profile(xml)
    assert p["logged_in"] is False
