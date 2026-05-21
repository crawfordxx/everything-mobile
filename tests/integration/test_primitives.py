"""Integration tests -- require EM_INTEGRATION=1 and the test device connected."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


@pytest.fixture(scope="module")
def device_serial() -> str:
    """Resolve test device via env (EM_TEST_SERIAL) or fall back to the first
    online device. Skip the suite cleanly if no device is connected."""
    requested = os.environ.get("EM_TEST_SERIAL")
    r = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=False)
    online = [line.split("\t")[0].strip() for line in r.stdout.splitlines() if "\tdevice" in line]
    if not online:
        pytest.skip("no device connected; set EM_TEST_SERIAL or attach a device")
    if requested:
        if requested not in online:
            pytest.skip(f"requested EM_TEST_SERIAL={requested} not online (have {online})")
        return requested
    return online[0]


def _cli(*args: str) -> dict:
    r = subprocess.run(
        [sys.executable, "-m", "mobilecli", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return json.loads(r.stdout)


@pytest.mark.integration
def test_devices_lists_test_device(device_serial: str):
    payload = _cli("devices")
    assert payload["ok"] is True, payload
    serials = [d["serial"] for d in payload["data"]["devices"]]
    assert device_serial in serials


@pytest.mark.integration
def test_screenshot_returns_valid_path(device_serial: str, tmp_path):
    out_path = tmp_path / "screen.png"
    payload = _cli("--serial", device_serial, "screenshot", "-o", str(out_path))
    assert payload["ok"] is True, payload
    assert payload["data"]["path"] == str(out_path)
    assert payload["data"]["size"] > 10_000
    assert payload["data"]["width"] > 0
    assert payload["data"]["height"] > 0
    assert out_path.exists()


@pytest.mark.integration
def test_doctor_returns_checks(device_serial: str):
    payload = _cli("--serial", device_serial, "doctor")
    assert payload["ok"] is True, payload
    checks = payload["data"]["checks"]
    assert any(c["name"] == "adb_available" for c in checks)
    assert any(c["name"] == "device_online" for c in checks)
    assert all("status" in c for c in checks)
