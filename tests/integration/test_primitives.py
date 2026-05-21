"""Integration tests -- require EM_INTEGRATION=1 and the test device connected."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

EXPECTED_SERIAL = "EXAMPLE-SERIAL"


@pytest.fixture(scope="module")
def device_serial() -> str:
    r = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=False)
    if EXPECTED_SERIAL not in r.stdout:
        pytest.skip(f"test device {EXPECTED_SERIAL} not connected")
    return EXPECTED_SERIAL


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
def test_tap_at_safe_coords(device_serial: str):
    """Humanized tap jitters ±8 px around target and emits non-zero duration."""
    payload = _cli("--serial", device_serial, "tap", "100", "100")
    assert payload["ok"] is True, payload
    assert abs(payload["data"]["x"] - 100) <= 8
    assert abs(payload["data"]["y"] - 100) <= 8
    assert payload["data"]["duration_ms"] > 0


@pytest.mark.integration
def test_swipe_short(device_serial: str):
    payload = _cli("--serial", device_serial, "swipe", "100", "100", "100", "200")
    assert payload["ok"] is True, payload
    assert payload["data"]["duration_ms"] >= 0


@pytest.mark.integration
def test_keyevent_back(device_serial: str):
    payload = _cli("--serial", device_serial, "keyevent", "back")
    assert payload["ok"] is True, payload


@pytest.mark.integration
def test_dump_creates_xml(device_serial: str, tmp_path):
    out = tmp_path / "ui.xml"
    payload = _cli("--serial", device_serial, "dump", "-o", str(out))
    assert payload["ok"] is True, payload
    assert payload["data"]["size"] > 100
    assert out.exists()


@pytest.mark.integration
def test_launch_settings(device_serial: str):
    payload = _cli("--serial", device_serial, "launch", "com.android.settings")
    assert payload["ok"] is True, payload


@pytest.mark.integration
def test_foreground_after_launch(device_serial: str):
    _cli("--serial", device_serial, "launch", "com.android.settings")
    payload = _cli("--serial", device_serial, "foreground")
    assert payload["ok"] is True, payload
    assert "settings" in payload["data"]["package"].lower()


@pytest.mark.integration
def test_doctor_returns_checks(device_serial: str):
    payload = _cli("--serial", device_serial, "doctor")
    assert payload["ok"] is True, payload
    checks = payload["data"]["checks"]
    assert any(c["name"] == "adb_available" for c in checks)
    assert any(c["name"] == "device_online" for c in checks)
    assert all("status" in c for c in checks)


@pytest.mark.integration
def test_type_ascii(device_serial: str):
    payload = _cli("--serial", device_serial, "type", "hello")
    assert payload["ok"] is True, payload
    assert payload["data"]["chars"] == 5
