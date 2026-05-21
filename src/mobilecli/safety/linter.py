"""ContentLinter -- refuse text that platforms flag as instant shadowban."""

from __future__ import annotations

import re

from mobilecli.envelope import EmError, ErrorCode

DEFAULT_BANNED_PATTERNS: list[str] = [
    r"加.{0,4}微信",
    r"加.{0,4}V.{0,4}[X信]",
    r"VX[\s:：]*\w+",
    r"扫.{0,3}码",
    r"扫.{0,3}二维码",
    r"戳我",
    r"私我",
    r"滴滴我",
    r"\b1[3-9]\d{9}\b",
    r"q[qQ][\s:：]*\d{5,}",
    r"wx[\s:：]*\w+",
]


class ContentLinter:
    def __init__(self, extra_patterns: list[str] | None = None) -> None:
        patterns = list(DEFAULT_BANNED_PATTERNS) + list(extra_patterns or [])
        self._regexes = [re.compile(p, re.IGNORECASE) for p in patterns]

    def check_or_raise(self, text: str) -> None:
        for rx in self._regexes:
            m = rx.search(text)
            if m:
                raise EmError(
                    ErrorCode.CONTENT_BANNED,
                    f"banned phrase: {m.group(0)!r}",
                    hint="rewrite without contact info / 引流 patterns",
                )
