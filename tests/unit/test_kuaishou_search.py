"""Tests for kuaishou search result-card parsing (_result_cards).

Pure logic over UI dump XML (synthetic fixtures, no PII). The search results
page uses clickable `id/container` grid cells; older layouts used
`play_view_container` (kept as a fallback).
"""

from __future__ import annotations

from mobilecli.apps.kuaishou import _result_cards

# 新版搜索页:可点 container 网格卡。含 1 个非 clickable header + 1 个细条,应被过滤。
_NEW = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node resource-id="com.smile.gifmaker:id/container" class="android.widget.RelativeLayout" clickable="true" bounds="[10,562][535,1776]"/>
  <node resource-id="com.smile.gifmaker:id/container" class="android.widget.RelativeLayout" clickable="true" bounds="[545,562][1070,1520]"/>
  <node resource-id="com.smile.gifmaker:id/container" class="android.widget.RelativeLayout" clickable="true" bounds="[10,1786][535,2347]"/>
  <node resource-id="com.smile.gifmaker:id/container" class="android.widget.RelativeLayout" clickable="false" bounds="[0,0][1080,80]"/>
  <node resource-id="com.smile.gifmaker:id/container" class="android.widget.LinearLayout" clickable="true" bounds="[0,100][1080,140]"/>
</hierarchy>"""

# 旧版搜索页:play_view_container(回退路径)。
_OLD = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node resource-id="com.smile.gifmaker:id/play_view_container" class="android.widget.FrameLayout" clickable="true" bounds="[10,560][535,1260]"/>
  <node resource-id="com.smile.gifmaker:id/play_view_container" class="android.widget.FrameLayout" clickable="true" bounds="[545,560][1070,1260]"/>
</hierarchy>"""


def test_result_cards_new_layout_filters_to_grid_cells():
    cards = _result_cards(_NEW)
    # 3 个达到卡片尺寸(宽>100 且 高>200)的 clickable container;
    # 非 clickable 的 header 和高仅 40 的细条被过滤。
    assert len(cards) == 3
    assert cards[0]["cx"] == (10 + 535) // 2
    assert cards[0]["cy"] == (562 + 1776) // 2


def test_result_cards_fallback_to_play_container():
    cards = _result_cards(_OLD)
    assert len(cards) == 2


def test_result_cards_none_when_empty():
    assert _result_cards("<hierarchy></hierarchy>") == []
