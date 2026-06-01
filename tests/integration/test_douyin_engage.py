"""Douyin like/reply integration -- EM_INTEGRATION=1 + connected device.

These DO NOT commit (dry-run only). Real-send is exercised manually / E2E.
Set EM_DOUYIN_KEYWORD to steer the search keyword (default 猫)."""

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
def test_douyin_like_dry_run_locates_button(serial: str):
    """search -> open -> like dry-run returns the like-button coords."""
    _cli("--serial", serial, "douyin", "launch")
    _cli("--serial", serial, "douyin", "search", "--keyword", os.environ.get("EM_DOUYIN_KEYWORD", "猫"))
    _cli("--serial", serial, "douyin", "open", "--rank", "1")
    payload = _cli("--serial", serial, "douyin", "like")  # no --commit
    assert payload["ok"] is True, payload
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["like_button_cx"] > 0


@pytest.mark.integration
def test_douyin_reply_dry_run_selects_and_locates_send(serial: str):
    """Self-contained: navigate fresh, don't depend on a prior test's screen."""
    _cli("--serial", serial, "douyin", "launch")
    _cli("--serial", serial, "douyin", "search", "--keyword", os.environ.get("EM_DOUYIN_KEYWORD", "猫"))
    _cli("--serial", serial, "douyin", "open", "--rank", "1")
    payload = _cli("--serial", serial, "douyin", "reply", "--rank", "1", "--text", "test")
    assert payload["ok"] is True, payload
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["target_index"] == 1
    assert payload["data"]["send_button_cx"] > 0
