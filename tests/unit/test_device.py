"""Tests for the ADB Device wrapper. Uses _select_serial directly to stay offline."""

from __future__ import annotations

import pytest

from mobilecli.adb.device import Device, _parse_devices_output  # noqa: F401
from mobilecli.envelope import EmError, ErrorCode


def test_parse_devices_output_normal():
    out = "List of devices attached\nEXAMPLE-SERIAL\tdevice\nemulator-5554\toffline\n"
    devs = _parse_devices_output(out)
    assert devs == [
        {"serial": "EXAMPLE-SERIAL", "state": "device"},
        {"serial": "emulator-5554", "state": "offline"},
    ]


def test_parse_devices_output_empty():
    assert _parse_devices_output("List of devices attached\n") == []


def test_select_serial_uses_only_connected_when_one():
    devices = [{"serial": "ABC", "state": "device"}]
    assert Device._select_serial(devices, requested=None) == "ABC"


def test_select_serial_requires_choice_when_many():
    devices = [
        {"serial": "ABC", "state": "device"},
        {"serial": "DEF", "state": "device"},
    ]
    with pytest.raises(EmError) as exc:
        Device._select_serial(devices, requested=None)
    assert exc.value.code is ErrorCode.MULTIPLE_DEVICES


def test_select_serial_uses_requested_if_present():
    devices = [
        {"serial": "ABC", "state": "device"},
        {"serial": "DEF", "state": "device"},
    ]
    assert Device._select_serial(devices, requested="DEF") == "DEF"


def test_select_serial_errors_on_no_devices():
    with pytest.raises(EmError) as exc:
        Device._select_serial([], requested=None)
    assert exc.value.code is ErrorCode.NO_DEVICE


def test_select_serial_ignores_offline_devices():
    devices = [
        {"serial": "ABC", "state": "offline"},
        {"serial": "DEF", "state": "device"},
    ]
    assert Device._select_serial(devices, requested=None) == "DEF"
