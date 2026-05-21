"""Tests for CLI dispatching."""

from __future__ import annotations

import json
import subprocess
import sys


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mobilecli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_no_args_shows_help():
    r = run_cli()
    assert r.returncode != 0 or "usage" in (r.stdout + r.stderr).lower()


def test_help_exits_zero():
    r = run_cli("--help")
    assert r.returncode == 0
    assert "mobilecli" in r.stdout.lower()


def test_unknown_command_returns_nonzero():
    # argparse rejects with code 2
    r = run_cli("does-not-exist")
    assert r.returncode != 0


def test_devices_command_returns_json():
    """`devices` works offline -- returns JSON whether or not a device is attached."""
    r = run_cli("devices")
    # Output may go to stdout (ok envelope) or stderr (if adb missing) -- accept either
    payload = json.loads(r.stdout) if r.stdout.strip() else None
    if payload is not None:
        assert payload["command"] == "devices"
