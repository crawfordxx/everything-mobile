"""Xiaohongshu reply integration -- EM_INTEGRATION=1 + connected device.

dry-run only (no commit). The reply verb scrolls comments into view itself.
Set EM_XHS_KEYWORD to steer the search keyword (default 穿搭)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


def _cli(*args: str) -> dict:
    r = subprocess.run(
        [sys.executable, "-m", "mobilecli", *args],
        capture_output=True, text=True, check=False,
    )
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def serial() -> str:
    r = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=False)
    online = [ln.split("\t")[0].strip() for ln in r.stdout.splitlines() if "\tdevice" in ln]
    if not online:
        pytest.skip("no device connected")
    return online[0]


@pytest.mark.integration
def test_xhs_reply_dry_run_selects_and_locates_send(serial: str):
    _cli("--serial", serial, "xiaohongshu", "launch")
    _cli("--serial", serial, "xiaohongshu", "search", "--keyword", os.environ.get("EM_XHS_KEYWORD", "穿搭"))
    _cli("--serial", serial, "xiaohongshu", "open", "--rank", "1")
    # reply verb scrolls comments into view itself (no manual scroll needed)
    payload = _cli("--serial", serial, "xiaohongshu", "reply", "--rank", "1", "--text", "nice")
    assert payload["ok"] is True, payload
    assert payload["data"]["dry_run"] is True
    # send_btn is only located after the compose (mContentET) opened, so this
    # also proves the 回复 tap opened the reply compose:
    assert payload["data"]["send_button_cx"] > 0
