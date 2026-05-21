"""JSON envelope wrapper for CLI commands.

All commands return a stable JSON shape:
  success: {"ok": true,  "command": ..., "device": ..., "elapsed_ms": int, "data":  {...}}
  failure: {"ok": false, "command": ..., "device": ..., "elapsed_ms": int, "error": {"code", "message", "hint"}}
"""

from __future__ import annotations

import enum
import functools
import json
import time
from collections.abc import Callable
from typing import Any


class ErrorCode(str, enum.Enum):
    NO_DEVICE = "NO_DEVICE"
    MULTIPLE_DEVICES = "MULTIPLE_DEVICES"
    ADB_TIMEOUT = "ADB_TIMEOUT"
    APP_NOT_INSTALLED = "APP_NOT_INSTALLED"
    APP_NOT_FOREGROUND = "APP_NOT_FOREGROUND"
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    IME_NOT_SET = "IME_NOT_SET"
    COMMIT_REFUSED = "COMMIT_REFUSED"
    RATE_LIMITED = "RATE_LIMITED"
    CONTENT_BANNED = "CONTENT_BANNED"
    WARMUP_REQUIRED = "WARMUP_REQUIRED"
    UNKNOWN = "UNKNOWN"


class EmError(Exception):
    """Library-side typed error mapped to an ErrorCode + hint."""

    def __init__(self, code: ErrorCode, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


def envelope(*, command: str) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., str]]:
    """Decorator that wraps a verb function into a JSON-emitting CLI command.

    The wrapped function must accept `device: str` as a keyword arg and return a dict.
    Exceptions are caught and mapped: EmError -> code/message/hint, anything else -> UNKNOWN.
    """

    def decorator(fn: Callable[..., dict[str, Any]]) -> Callable[..., str]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            device = kwargs.get("device", "")
            t0 = time.monotonic()
            try:
                data = fn(*args, **kwargs)
                payload: dict[str, Any] = {
                    "ok": True,
                    "command": command,
                    "device": device,
                    "elapsed_ms": int((time.monotonic() - t0) * 1000),
                    "data": data,
                }
            except EmError as err:
                payload = {
                    "ok": False,
                    "command": command,
                    "device": device,
                    "elapsed_ms": int((time.monotonic() - t0) * 1000),
                    "error": {
                        "code": err.code.value,
                        "message": err.message,
                        "hint": err.hint,
                    },
                }
            except Exception as exc:  # noqa: BLE001
                payload = {
                    "ok": False,
                    "command": command,
                    "device": device,
                    "elapsed_ms": int((time.monotonic() - t0) * 1000),
                    "error": {
                        "code": ErrorCode.UNKNOWN.value,
                        "message": str(exc) or exc.__class__.__name__,
                        "hint": "run with --verbose for stack trace",
                    },
                }
            return json.dumps(payload, ensure_ascii=False)

        return wrapper

    return decorator
