"""Wiring tests for douyin / kuaishou publish verbs.

The device UI walk is recon-pending (integration-tested later); here we pin the
verb registration, commit-gate, daily cap, and the full arg surface
(--media/--title/--body/--tags/--cover/--declare) that mirror xiaohongshu.
"""

from __future__ import annotations

import argparse

import pytest

from mobilecli.apps.douyin import app as douyin_app
from mobilecli.apps.kuaishou import app as kuaishou_app


def _publish_parser(app) -> argparse.ArgumentParser:
    verb = app.verbs["publish"]
    p = argparse.ArgumentParser()
    assert verb.add_args is not None
    verb.add_args(p)
    return p


@pytest.mark.parametrize("app", [douyin_app, kuaishou_app])
def test_publish_registered_with_commit_gate_and_cap(app):
    assert "publish" in app.verbs
    assert app.verbs["publish"].requires_commit_flag is True
    assert app.daily_caps.get("publish") == 5


@pytest.mark.parametrize("app", [douyin_app, kuaishou_app])
def test_publish_arg_surface(app):
    p = _publish_parser(app)
    ns = p.parse_args(
        [
            "--media",
            "a.jpg",
            "b.jpg",
            "--title",
            "标题",
            "--body",
            "正文",
            "--tags",
            "x,y",
            "--cover",
            "1",
            "--declare",
            "original",
        ]
    )
    assert ns.media == ["a.jpg", "b.jpg"]
    assert ns.title == "标题"
    assert ns.body == "正文"
    assert ns.tags == "x,y"
    assert ns.cover == "1"
    assert ns.declare == "original"


@pytest.mark.parametrize("app", [douyin_app, kuaishou_app])
def test_publish_declare_defaults_none(app):
    p = _publish_parser(app)
    ns = p.parse_args(["--media", "v.mp4", "--title", "t", "--body", "b"])
    assert ns.declare == "none"
    assert ns.tags is None
    assert ns.cover is None
