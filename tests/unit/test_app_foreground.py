"""Tests for core.app foreground-activity parsing.

foreground() 此前只解析 `dumpsys window` 的 mCurrentFocus(焦点窗口):弹窗/
输入法/toast 占住焦点时,焦点窗口 ≠ 当前页面,导致 kuaishou _on_home 在已回
首页时仍判 False → 连按 4 次 BACK + force-stop(真机实测把快手退出、抖音任务
浮到前台)。修复:优先 `dumpsys activity activities` 的 topResumedActivity,
mCurrentFocus 仅作回退。样例输出为真机格式的合成数据。
"""

from __future__ import annotations

from mobilecli.core.app import parse_current_focus, parse_top_resumed

_ACTIVITY_OUT = """\
ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)
Display #0 (activities from top to bottom):
  * Task{8c042f1 #184 type=standard A=10341:com.smile.gifmaker U=0 visible=true}
    topResumedActivity=ActivityRecord{200883241 u0 com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity t184}
"""

_ACTIVITY_OUT_RELATIVE = """\
    topResumedActivity=ActivityRecord{15326432 u0 com.ss.android.ugc.aweme/.splash.SplashActivity t180}
"""

_WINDOW_OUT = """\
  mCurrentFocus=Window{2a38a96 u0 com.smile.gifmaker/com.yxcorp.plugin.search.SearchActivity}
"""

_WINDOW_OUT_IME = """\
  mCurrentFocus=Window{7e11f02 u0 InputMethod}
"""


def test_parse_top_resumed_standard():
    fg = parse_top_resumed(_ACTIVITY_OUT)
    assert fg == {
        "package": "com.smile.gifmaker",
        "activity": "com.yxcorp.gifshow.HomeActivity",
    }


def test_parse_top_resumed_relative_activity_name():
    # activity 可能是相对名(.splash.SplashActivity);endswith 后缀判断仍可用
    fg = parse_top_resumed(_ACTIVITY_OUT_RELATIVE)
    assert fg == {
        "package": "com.ss.android.ugc.aweme",
        "activity": ".splash.SplashActivity",
    }


def test_parse_top_resumed_none_when_absent():
    assert parse_top_resumed("ACTIVITY MANAGER ACTIVITIES\n") is None


def test_parse_current_focus_standard():
    fg = parse_current_focus(_WINDOW_OUT)
    assert fg == {
        "package": "com.smile.gifmaker",
        "activity": "com.yxcorp.plugin.search.SearchActivity",
    }


def test_parse_current_focus_ime_window_is_not_an_activity():
    # 输入法窗口占焦点时 mCurrentFocus 不含 包名/Activity —— 不可作为页面判据
    assert parse_current_focus(_WINDOW_OUT_IME) is None
