"""Plugin framework tests -- App / Verb / registry / ExecContext build."""

from __future__ import annotations

from mobilecli.plugin import App
from mobilecli.plugin.registry import load


def test_app_register_verb_via_decorator():
    a = App(name="demo", package="com.example.demo")

    @a.verb("hello")
    def hello(args, ctx):
        return {"greeting": "hi"}

    assert "hello" in a.verbs
    assert a.get_verb("hello") is hello


def test_app_unknown_verb_returns_none():
    a = App(name="demo", package="com.example.demo")
    assert a.get_verb("nope") is None


def test_registry_loads_builtin_apps():
    apps = load()
    assert "douyin" in apps
    assert "xiaohongshu" in apps
    assert apps["douyin"].package == "com.ss.android.ugc.aweme"
    assert apps["xiaohongshu"].package == "com.xingin.xhs"


def test_builtin_app_verbs_present():
    apps = load()
    for verb_name in ("launch", "search", "open", "detail", "comment"):
        assert verb_name in apps["douyin"].verbs, f"douyin missing {verb_name}"
        assert verb_name in apps["xiaohongshu"].verbs, f"xiaohongshu missing {verb_name}"


def test_douyin_comment_requires_commit_flag():
    apps = load()
    assert apps["douyin"].verbs["comment"].requires_commit_flag is True


def test_xiaohongshu_comment_does_not_require_commit_flag():
    """v1 lock: XHS comment is dry-run only, no --commit path exists."""
    apps = load()
    assert apps["xiaohongshu"].verbs["comment"].requires_commit_flag is False
