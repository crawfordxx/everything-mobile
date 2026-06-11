"""Tests for kuaishou search result-card selection (_result_cards).

2026-06 快手搜索结果页改版:综合 tab 按关键词 A/B 出「双列网格 / 单列 feed」两种
布局,且混入商家/用户/广告等非视频卡。_result_cards 只选视频卡:
- 网格布局:content-desc「××的作品」(剔除带「广告」角标的推广卡);
- feed 布局:内含 id/play_view_container 的卡,tap 锚点取预览区中心;
- 旧版回退:play_view_container 本身。
fixtures 为真机 dump 的匿名化版本(结构/坐标保真,文案合成)。
"""

from __future__ import annotations

from pathlib import Path

from mobilecli.apps.kuaishou import _result_cards

FIX = Path(__file__).parent.parent / "fixtures"


def _grid() -> str:
    return (FIX / "kuaishou-search-grid.xml").read_text()


def _feed() -> str:
    return (FIX / "kuaishou-search-feed.xml").read_text()


# 旧版搜索页:play_view_container(回退路径)。
_OLD = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node resource-id="com.smile.gifmaker:id/play_view_container" class="android.widget.FrameLayout" clickable="true" bounds="[10,560][535,1260]"/>
  <node resource-id="com.smile.gifmaker:id/play_view_container" class="android.widget.FrameLayout" clickable="true" bounds="[545,560][1070,1260]"/>
</hierarchy>"""


def test_grid_layout_selects_only_work_cards():
    cards = _result_cards(_grid())
    # 4 张可点 container:视频卡 A/B + 广告卡(「广告」角标)+ 商家卡(无「的作品」)。
    # 只留 2 张视频卡,文档顺序。
    assert [c["content_desc"] for c in cards] == ["测试号A的作品", "测试号B的作品"]
    assert cards[0]["bounds"] == [10, 562, 535, 1610]


def test_grid_layout_excludes_ad_and_merchant_cards():
    descs = [c["content_desc"] for c in _result_cards(_grid())]
    assert "推广号C的作品" not in descs  # 广告卡(desc 也带「的作品」,靠角标剔除)
    assert "" not in descs  # 商家/用户卡(无「的作品」desc)


def test_feed_layout_anchors_tap_on_play_container():
    cards = _result_cards(_feed())
    assert len(cards) == 1
    # tap 锚点 = play_view_container 中心(整卡中心可能落在作者行 → 误进用户主页)
    assert cards[0]["cx"] == (49 + 707) // 2
    assert cards[0]["cy"] == (798 + 1675) // 2
    assert cards[0]["bounds"] == [49, 798, 707, 1675]


def test_feed_layout_drops_bottom_band_card():
    # 底部裁剩的视频卡 2(锚点 cy=2300 已进底部导航带):必须丢弃。
    # open 用 search 返回的坐标盲点,若届时页面已退回首页,(540,2283) 附近正是
    # 「拍摄」按钮 —— 留着这张卡就是把相机入口当成搜索结果回传。
    for c in _result_cards(_feed()):
        assert c["bounds"] != [49, 2253, 707, 2347]


def test_feed_layout_skips_merchant_card():
    # 商家卡(无 play_view_container)夹在两张视频卡之间,应被整张跳过
    descs = [c["bounds"] for c in _result_cards(_feed())]
    assert [c[1] for c in descs] == [798]  # 仅剩视频卡 1(商家卡/底部裁剩卡都不在)


def test_grid_layout_drops_bottom_band_card():
    # 网格布局同样过滤:锚点落在底部导航带的裁剩视频卡不回传
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node class="android.widget.FrameLayout" bounds="[0,0][1080,2347]">
    <node resource-id="com.smile.gifmaker:id/container" content-desc="测试号A的作品" class="android.view.ViewGroup" clickable="true" bounds="[10,562][535,1610]"/>
    <node resource-id="com.smile.gifmaker:id/container" content-desc="测试号B的作品" class="android.view.ViewGroup" clickable="true" bounds="[10,2128][535,2347]"/>
  </node>
</hierarchy>"""
    cards = _result_cards(xml)
    assert [c["content_desc"] for c in cards] == ["测试号A的作品"]


def test_feed_layout_drops_sliver_play_container():
    # 预览区只剩 ≤50px 的碎条不可稳定点击,该卡应被丢弃(另一张正常卡保留)
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node resource-id="com.smile.gifmaker:id/container" class="android.view.ViewGroup" clickable="true" bounds="[0,552][1080,1900]">
    <node resource-id="com.smile.gifmaker:id/play_view_container" class="android.view.ViewGroup" clickable="true" bounds="[49,798][707,1675]"/>
  </node>
  <node resource-id="com.smile.gifmaker:id/container" class="android.view.ViewGroup" clickable="true" bounds="[0,2300][1080,2347]">
    <node resource-id="com.smile.gifmaker:id/play_view_container" class="android.view.ViewGroup" clickable="true" bounds="[49,2307][707,2347]"/>
  </node>
</hierarchy>"""
    cards = _result_cards(xml)
    assert len(cards) == 1
    assert cards[0]["bounds"] == [49, 798, 707, 1675]


def test_result_cards_fallback_to_play_container():
    cards = _result_cards(_OLD)
    assert len(cards) == 2


def test_result_cards_none_when_empty():
    assert _result_cards("<hierarchy></hierarchy>") == []
