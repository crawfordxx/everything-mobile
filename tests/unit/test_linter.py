"""ContentLinter: block 加微信 / VX / phone / QR / 戳我 families."""

from __future__ import annotations

import pytest

from mobilecli.envelope import EmError, ErrorCode
from mobilecli.safety.linter import ContentLinter


def test_clean_text_passes():
    ContentLinter().check_or_raise("学到了 👍")
    ContentLinter().check_or_raise("好棒的内容~")
    ContentLinter().check_or_raise("get a hello world tutorial")


@pytest.mark.parametrize(
    "text",
    [
        "戳我学短剧",
        "私我看更多",
        "加微信 abc123",
        "加 V 信 secret",
        "扫码进群",
        "扫二维码加我",
        "VX:newuser",
        "13912345678 联系我",
        "qq: 123456789",
        "wx:newuser_2026",
    ],
)
def test_banned_phrase_raises(text):
    with pytest.raises(EmError) as exc:
        ContentLinter().check_or_raise(text)
    assert exc.value.code is ErrorCode.CONTENT_BANNED


def test_extra_patterns_compose():
    linter = ContentLinter(extra_patterns=[r"内部测试"])
    with pytest.raises(EmError):
        linter.check_or_raise("欢迎参与内部测试")
