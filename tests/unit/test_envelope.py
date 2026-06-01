"""Tests for the JSON envelope wrapper."""

from __future__ import annotations

import json

from mobilecli.envelope import EmError, ErrorCode, envelope


def test_envelope_success_wraps_dict():
    @envelope(command="example")
    def fn(*, device: str) -> dict:
        return {"hello": "world"}

    out = fn(device="ABC123")
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["command"] == "example"
    assert payload["device"] == "ABC123"
    assert payload["data"] == {"hello": "world"}
    assert isinstance(payload["elapsed_ms"], int)


def test_envelope_failure_from_em_error():
    @envelope(command="example")
    def fn(*, device: str) -> dict:
        raise EmError(ErrorCode.NO_DEVICE, "no device", hint="check usb")

    out = fn(device="")
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NO_DEVICE"
    assert payload["error"]["message"] == "no device"
    assert payload["error"]["hint"] == "check usb"


def test_envelope_unknown_error_on_uncaught():
    @envelope(command="example")
    def fn(*, device: str) -> dict:
        raise RuntimeError("boom")

    out = fn(device="ABC123")
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "UNKNOWN"
    assert "boom" in payload["error"]["message"]


def test_envelope_chinese_not_escaped():
    @envelope(command="example")
    def fn(*, device: str) -> dict:
        return {"text": "学到了"}

    out = fn(device="ABC")
    assert "学到了" in out
    assert "\\u" not in out


def test_new_error_codes_exist():
    from mobilecli.envelope import ErrorCode
    assert ErrorCode.INVALID_ARG.value == "INVALID_ARG"
    assert ErrorCode.PERMISSION_REQUIRED.value == "PERMISSION_REQUIRED"
    assert ErrorCode.MEDIA_NOT_INDEXED.value == "MEDIA_NOT_INDEXED"
